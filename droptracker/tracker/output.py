"""Calendar feed (.ics) + JSON for the dashboard."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .model import Drop


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines over 75 octets continue on the next line with a leading space."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        e = ch.encode("utf-8")
        if len(cur) + len(e) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += e
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def to_ics(drops: list[Drop], now: datetime, alarm_minutes: int = 15,
           all_day_alarm_hour: int = 9) -> str:
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//droptracker//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
         "X-WR-CALNAME:Card Drops", "X-PUBLISHED-TTL:PT1H",
         "REFRESH-INTERVAL;VALUE=DURATION:PT1H"]
    for d in drops:
        if not d.when():
            continue
        prefix = {"preorder": "PREORDER", "release": "RELEASE", "drop": "DROP", "news": "NEWS",
                  "lottery": "LOTTERY"}.get(d.kind, d.kind.upper())
        summary = f"{prefix} [{d.game}] {d.title}" + (f" ({d.price})" if d.price else "")
        desc = "\n".join(x for x in [d.note, f"Source: {d.source}", d.url] if x)
        L += ["BEGIN:VEVENT", f"UID:{d.id}@droptracker", f"DTSTAMP:{_utc(now)}",
              _fold("SUMMARY:" + _esc(summary)), _fold("DESCRIPTION:" + _esc(desc))]
        if d.url:
            L.append(_fold("URL:" + d.url))
        if d.start:
            L += [f"DTSTART:{_utc(d.start)}", f"DTEND:{_utc(d.start + timedelta(minutes=30))}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", _fold("DESCRIPTION:" + _esc(summary)),
                  f"TRIGGER:-PT{alarm_minutes}M", "END:VALARM"]
        else:
            day = d.day
            L += [f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
                  "TRANSP:TRANSPARENT"]
            if d.kind in ("preorder", "drop", "release", "lottery"):
                L += ["BEGIN:VALARM", "ACTION:DISPLAY", _fold("DESCRIPTION:" + _esc(summary)),
                      f"TRIGGER:PT{all_day_alarm_hour}H", "END:VALARM"]
        L.append("END:VEVENT")
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def to_json(drops: list[Drop], now: datetime) -> str:
    return json.dumps({"generated": now.astimezone(timezone.utc).isoformat(),
                       "drops": [d.to_dict() for d in drops]}, indent=1)


def window(drops: list[Drop], now: datetime, past_days: int = 21, future_days: int = 180) -> list[Drop]:
    lo, hi = (now - timedelta(days=past_days)).date(), (now + timedelta(days=future_days)).date()
    keep = [d for d in drops if d.when() is None or lo <= d.when() <= hi]
    return sorted(keep, key=lambda d: (d.when() is None, d.when() or now.date(),
                                       (d.start or now).timestamp(), d.game, d.title))
