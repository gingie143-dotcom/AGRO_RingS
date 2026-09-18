"""Single dispatcher with PostgreSQL advisory lock; no automatic redial after uncertainty."""

import logging
import time
import httpx
from sqlalchemy import select, text
from .config import settings
from .db import engine, SessionLocal
from .models import Call, Campaign, Scenario, Agent, Contact, now
from .domain import dispatch_one, finish, utc, ACTIVE, eligible

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("worker")


def tick():
    with SessionLocal() as db:
        for call in db.scalars(select(Call).where(Call.status.in_(ACTIVE))).all():
            if (now() - utc(call.created_at)).total_seconds() > settings().max_call_seconds + 60:
                finish(db, call, "failed", "watchdog_timeout", {})
        call = dispatch_one(db)
        db.commit()
        if not call:
            return
        campaign = db.get(Campaign, call.campaign_id)
        scenario = db.get(Scenario, campaign.scenario_id)
        agent = db.get(Agent, campaign.agent_id)
        contact = db.get(Contact, call.contact_id)
        # Recheck eligibility immediately before dispatch.
        db.refresh(contact)
        db.refresh(campaign)
        if not eligible(db, contact) or campaign.status != "running":
            finish(db, call, "cancelled", "policy_changed", {})
            db.commit()
            return
        payload = {
            "call_id": call.id,
            "mode": call.mode,
            "instructions": scenario.instructions
            + "\nЦель: "
            + scenario.goal
            + "\n"
            + agent.instructions,
            "voice": agent.voice,
        }
        try:
            response = httpx.post(
                settings().gateway_url + "/sessions",
                json=payload,
                headers={"Authorization": "Bearer " + settings().service_token},
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Commit first, send once. Uncertain delivery is failed, never blindly redialed.
            db.refresh(call)
            if call.status in ACTIVE:
                finish(db, call, "failed", "dispatch_uncertain", {})
                db.commit()
            log.error('{"event":"dispatch_failed","call_id":"%s"}', call.id)


def main():
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Production worker requires PostgreSQL advisory locks")
    while True:
        try:
            with engine.connect() as lock:
                acquired = lock.scalar(text("SELECT pg_try_advisory_lock(481726)"))
                if not acquired:
                    time.sleep(2)
                    continue
                try:
                    while True:
                        lock.execute(text("SELECT 1"))
                        tick()
                        time.sleep(1)
                finally:
                    lock.execute(text("SELECT pg_advisory_unlock(481726)"))
        except Exception as exc:
            log.error('{"event":"worker_error","type":"%s"}', type(exc).__name__)
            time.sleep(3)


if __name__ == "__main__":
    main()
