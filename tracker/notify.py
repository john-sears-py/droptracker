"""Phone alerts. ntfy.sh is free: install the ntfy app, subscribe to your topic,
set NTFY_TOPIC. Discord webhook is optional. With neither set, alerts print only.

Every alert carries the buy link three ways, so it survives any client:
  1. tapping the notification opens it           (ntfy "Click")
  2. a labelled button: "Enter lottery", "Pre-order now", ...   (ntfy "Actions")
  3. the URL printed at the end of the message    (works in Discord / any app)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from .model import Drop

BUTTON = {
    "lottery": "Enter lottery",
    "preorder": "Pre-order now",
    "drop": "Open drop page",
    "release": "View product",
    "news": "Read post",
}


def _fmt(d: Drop, tz) -> str:
    when = d.start.astimezone(tz).strftime("%a %b %d %I:%M %p %Z") if d.start else (str(d.day) if d.day else "")
    return " | ".join(x for x in [when, d.price, d.note, d.source] if x)


def _actions(buttons: list[tuple[str, str]]) -> str:
    """ntfy action header: 'view, <label>, <url>, clear=true; ...' (max 3 buttons).
    Labels must not contain commas or semicolons - they're the header's separators."""
    parts = []
    for label, url in buttons[:3]:
        if not url:
            continue
        label = label.replace(",", " ").replace(";", " ")
        parts.append(f"view, {label}, {url}, clear=true")
    return "; ".join(parts)


def send(session, title: str, body: str, url: str = "", priority: str = "default", tags: str = "",
         buttons: list[tuple[str, str]] | None = None):
    sent = False
    if url and url not in body:
        body = f"{body}\n{url}" if body else url
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        headers = {"Title": title.encode("utf-8"), "Priority": priority}
        if url:
            headers["Click"] = url
        if tags:
            headers["Tags"] = tags
        act = _actions(buttons or ([("Open", url)] if url else []))
        if act:
            headers["Actions"] = act
        session.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=15)
        sent = True
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook:
        session.post(hook, json={"content": f"**{title}**\n{body}"[:1900]}, timeout=15)
        sent = True
    if not sent:
        print(f"[alert] {title} :: {body}")


def _buttons(d: Drop, dashboard: str | None) -> list[tuple[str, str]]:
    b = [(BUTTON.get(d.kind, "Open"), d.action_url())]
    if d.buy_url and d.url and d.buy_url != d.url:
        b.append(("Details", d.url))          # e.g. official product page vs. Premium Bandai store
    if dashboard:
        b.append(("Dashboard", dashboard))
    return b


def new_drop(session, d: Drop, tz, dashboard: str | None = None):
    label = {"preorder": "Pre-order", "release": "New product", "drop": "Drop", "news": "News",
             "lottery": "LOTTERY OPEN"}.get(d.kind, d.kind)
    hot = d.premium or d.kind in ("preorder", "drop", "lottery")
    send(session, f"{label}: [{d.game}] {d.title}"[:180], _fmt(d, tz), d.action_url(),
         priority="urgent" if d.kind == "lottery" else ("high" if hot else "default"),
         tags="ticket" if d.kind == "lottery" else ("rotating_light" if hot else ""),
         buttons=_buttons(d, dashboard))


def due_reminders(drops: list[Drop], reminded: dict, now: datetime, lead_minutes: int = 60) -> list[Drop]:
    """Timed drops starting within `lead_minutes` that haven't been reminded yet."""
    out = []
    for d in drops:
        if d.start and d.id not in reminded and now <= d.start <= now + timedelta(minutes=lead_minutes):
            out.append(d)
    return out


def reminder(session, d: Drop, tz, now: datetime, dashboard: str | None = None):
    mins = max(0, int((d.start - now).total_seconds() // 60))
    send(session, f"In {mins} min: [{d.game}] {d.title}"[:180], _fmt(d, tz), d.action_url(),
         priority="urgent", tags="alarm_clock", buttons=_buttons(d, dashboard))
