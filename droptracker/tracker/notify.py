"""Phone alerts. ntfy.sh is free: install the ntfy app, subscribe to your topic,
set NTFY_TOPIC. Discord webhook is optional. With neither set, alerts print only."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from .model import Drop


def _fmt(d: Drop, tz) -> str:
    when = d.start.astimezone(tz).strftime("%a %b %d %I:%M %p %Z") if d.start else (str(d.day) if d.day else "")
    return " | ".join(x for x in [when, d.price, d.note, d.source] if x)


def send(session, title: str, body: str, url: str = "", priority: str = "default", tags: str = ""):
    sent = False
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        headers = {"Title": title.encode("utf-8"), "Priority": priority}
        if url:
            headers["Click"] = url
        if tags:
            headers["Tags"] = tags
        session.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=15)
        sent = True
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook:
        session.post(hook, json={"content": f"**{title}**\n{body}\n{url}"[:1900]}, timeout=15)
        sent = True
    if not sent:
        print(f"[alert] {title} :: {body} {url}")


def new_drop(session, d: Drop, tz):
    label = {"preorder": "Pre-order", "release": "New product", "drop": "Drop", "news": "News",
             "lottery": "LOTTERY OPEN"}.get(d.kind, d.kind)
    hot = d.premium or d.kind in ("preorder", "drop", "lottery")
    send(session, f"{label}: [{d.game}] {d.title}"[:180], _fmt(d, tz), d.url,
         priority="urgent" if d.kind == "lottery" else ("high" if hot else "default"),
         tags="ticket" if d.kind == "lottery" else ("rotating_light" if hot else ""))


def due_reminders(drops: list[Drop], reminded: dict, now: datetime, lead_minutes: int = 60) -> list[Drop]:
    """Timed drops starting within `lead_minutes` that haven't been reminded yet."""
    out = []
    for d in drops:
        if d.start and d.id not in reminded and now <= d.start <= now + timedelta(minutes=lead_minutes):
            out.append(d)
    return out


def reminder(session, d: Drop, tz, now: datetime):
    mins = max(0, int((d.start - now).total_seconds() // 60))
    send(session, f"In {mins} min: [{d.game}] {d.title}"[:180], _fmt(d, tz), d.url,
         priority="urgent", tags="alarm_clock")
