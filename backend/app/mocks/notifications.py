"""Mock WhatsApp / email gateway. Nothing is actually sent: messages are logged and recorded as Nudge rows
(channel whatsapp|email, status sent), which the admin Agent Console shows on Day 4."""

import logging
import uuid

log = logging.getLogger(__name__)
SENT: list[dict] = []  # in-process log for tests/demo


def send(channel: str, to: str, text: str) -> dict:
    msg = {"id": f"mock-{uuid.uuid4().hex[:10]}", "channel": channel, "to": to, "text": text, "status": "delivered (simulated)"}
    SENT.append(msg)
    del SENT[:-200]
    log.info("[mock %s] to %s: %s", channel, to, text[:120])
    return msg
