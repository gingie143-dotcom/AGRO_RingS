"""ARI adapter. Experimental until accepted against the user's SIP deployment."""

import re
import httpx
from .config import config


class AsteriskARI:
    def __init__(self):
        cfg = config()
        self.client = httpx.AsyncClient(
            base_url=cfg.ari_url + "/", auth=(cfg.ari_username, cfg.ari_password), timeout=10
        )

    async def request(self, method, path, **params):
        r = await self.client.request(method, path, params=params)
        if method == "DELETE" and r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json() if r.content else None

    async def originate(self, number, call_id):
        if not re.fullmatch(r"\+[1-9]\d{7,14}", number):
            raise ValueError("Invalid dial number")
        endpoint = config().sip_endpoint
        if not re.fullmatch(r"[A-Za-z0-9_-]+", endpoint):
            raise ValueError("Invalid endpoint")
        return await self.request(
            "POST",
            "channels",
            endpoint=f"PJSIP/{number}@{endpoint}",
            app="ai-caller",
            channelId=call_id,
            timeout=30,
        )

    async def hangup(self, call_id):
        return await self.request("DELETE", "channels/" + call_id)

    async def dtmf(self, call_id, digits):
        if not re.fullmatch(r"[0-9*#]{1,20}", digits):
            raise ValueError("Invalid DTMF")
        return await self.request("POST", "channels/" + call_id + "/dtmf", dtmf=digits)

    async def close(self):
        await self.client.aclose()
