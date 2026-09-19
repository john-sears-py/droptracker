"""Loose date parsing for the formats card sites actually print."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

_MDY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b")


def parse_month_day(text: str, today: date) -> date | None:
    """'April 24, 2026' -> date. 'October 13' (no year) -> the next October 13
    on or after `today`, minus a 60-day grace so a just-passed date keeps its year."""
    for m in _MDY.finditer(text or ""):
        mon = MONTHS.get(m.group(1).lower())
        if not mon:
            continue
        day = int(m.group(2))
        try:
            if m.group(3):
                return date(int(m.group(3)), mon, day)
            d = date(today.year, mon, day)
            if (today - d).days > 60:
                d = date(today.year + 1, mon, day)
            return d
        except ValueError:
            continue
    return None


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_rfc822(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return parse_iso(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
