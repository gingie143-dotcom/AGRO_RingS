from datetime import timezone, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func, update
from .models import (
    Contact,
    Suppression,
    Campaign,
    CampaignContact,
    Call,
    Conversation,
    Message,
    CallEvent,
    AuditLog,
    now,
)
from .security import phone_hash
from .config import settings

ACTIVE = ("queued", "ringing", "answered")
TERMINAL = ("completed", "failed", "cancelled", "transferred")


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def audit(db, actor, action, resource_id, **details):
    db.add(AuditLog(actor=actor, action=action, resource_id=resource_id, details=details))


def suppress(db, contact):
    contact.opted_out = True
    contact.status = "opted_out"
    hashed = phone_hash(contact.phone)
    if not db.scalar(select(Suppression).where(Suppression.phone_hash == hashed)):
        db.add(Suppression(phone_hash=hashed))
    db.execute(
        update(CampaignContact)
        .where(CampaignContact.contact_id == contact.id, CampaignContact.status == "queued")
        .values(status="skipped")
    )


def eligible(db, contact):
    return bool(
        contact
        and not contact.opted_out
        and contact.consent_basis.strip()
        and not db.scalar(
            select(Suppression.id).where(Suppression.phone_hash == phone_hash(contact.phone))
        )
    )


def in_schedule(campaign, timestamp):
    local = timestamp.astimezone(ZoneInfo(campaign.timezone))
    return (
        local.weekday() in campaign.weekdays
        and campaign.start_hour <= local.hour < campaign.end_hour
    )


def create_call(db, campaign, enrollment, contact):
    call = Call(
        campaign_id=campaign.id,
        contact_id=contact.id,
        campaign_contact_id=enrollment.id,
        mode=campaign.mode,
    )
    db.add(call)
    db.flush()
    db.add(Conversation(call_id=call.id))
    enrollment.status = "calling"
    enrollment.attempts += 1
    campaign.last_dispatch_at = now()
    return call


def dispatch_one(db):
    # Production singleton dispatch is additionally guarded by a PostgreSQL advisory lock.
    active = db.scalar(select(func.count()).select_from(Call).where(Call.status.in_(ACTIVE)))
    if active >= settings().max_concurrent_calls:
        return None
    stamp = now()
    campaigns = db.scalars(
        select(Campaign).where(Campaign.status == "running").order_by(Campaign.created_at)
    ).all()
    for campaign in campaigns:
        if not in_schedule(campaign, stamp):
            continue
        if (
            campaign.last_dispatch_at
            and (stamp - utc(campaign.last_dispatch_at)).total_seconds() < campaign.delay_seconds
        ):
            continue
        count = db.scalar(
            select(func.count())
            .select_from(Call)
            .where(Call.campaign_id == campaign.id, Call.status.in_(ACTIVE))
        )
        if count >= campaign.max_concurrent:
            continue
        candidates = db.scalars(
            select(CampaignContact)
            .where(CampaignContact.campaign_id == campaign.id, CampaignContact.status == "queued")
            .order_by(CampaignContact.created_at)
            .with_for_update(skip_locked=True)
        ).all()
        for entry in candidates:
            if entry.retry_at and utc(entry.retry_at) > stamp:
                continue
            contact = db.get(Contact, entry.contact_id)
            if not eligible(db, contact) or entry.attempts >= campaign.max_attempts:
                entry.status = "skipped"
                continue
            existing = db.scalar(
                select(Call.id).where(Call.contact_id == contact.id, Call.status.in_(ACTIVE))
            )
            if existing:
                continue
            if campaign.mode != "simulation":
                # Live campaign launch remains gated until the manual E2E acceptance test is recorded.
                campaign.status = "paused"
                audit(db, "worker", "live_campaign_gate", campaign.id)
                continue
            return create_call(db, campaign, entry, contact)
        if not candidates and count == 0:
            campaign.status = "completed"
    return None


def apply_event(db, call, event):
    if db.scalar(
        select(CallEvent.id).where(
            CallEvent.call_id == call.id, CallEvent.event_id == event.event_id
        )
    ):
        return False
    if call.status in TERMINAL:
        # Late events cannot resurrect a terminated call or append content after deletion/retention.
        return False
    contact = db.get(Contact, call.contact_id) if call.contact_id else None
    if event.kind == "ringing":
        if call.status != "queued":
            raise HTTPException(409, "Invalid call transition")
        call.status = "ringing"
    elif event.kind == "answered":
        if call.status not in ("queued", "ringing"):
            raise HTTPException(409, "Invalid call transition")
        call.status = "answered"
        call.started_at = now()
    elif event.kind == "transcript":
        if call.status != "answered" or not event.role:
            raise HTTPException(409, "Transcript requires an answered call and role")
        conversation = db.scalar(select(Conversation).where(Conversation.call_id == call.id))
        db.add(
            Message(
                conversation_id=conversation.id,
                event_id=event.event_id,
                role=event.role,
                text=event.text,
            )
        )
    elif event.kind == "opt_out":
        if contact:
            suppress(db, contact)
        finish(db, call, "completed", "opt_out", {})
    elif event.kind in ("completed", "failed", "transferred"):
        finish(db, call, event.kind, event.reason, event.result)
    db.add(CallEvent(call_id=call.id, event_id=event.event_id, kind=event.kind))
    return True


def finish(db, call, status, reason, result):
    call.status = status
    call.ended_at = now()
    call.end_reason = reason
    call.result = result
    if call.started_at:
        call.duration_seconds = max(0, (call.ended_at - utc(call.started_at)).total_seconds())
    if call.contact_id:
        contact = db.get(Contact, call.contact_id)
        contact.last_contact_at = call.ended_at
    if call.campaign_contact_id:
        entry = db.get(CampaignContact, call.campaign_contact_id)
        campaign = db.get(Campaign, call.campaign_id)
        entry.status = status
        if status == "failed":
            campaign.error_count += 1
            # Ambiguous dispatch timeout is never retried automatically: it may have dialed.
            retryable = reason in ("busy", "no_answer")
            if (
                retryable
                and entry.attempts < campaign.max_attempts
                and campaign.status == "running"
            ):
                entry.status = "queued"
                entry.retry_at = now() + timedelta(minutes=5)
            if campaign.error_count >= campaign.max_errors:
                campaign.status = "paused"
