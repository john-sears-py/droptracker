"""Timed drops you (or I) type in, for sites that block scrapers (Topps.com sits
behind a Cloudflare bot check; don't try to get around it - copy the time in)."""
from __future__ import annotations

from datetime import date

import yaml

from ..dates import parse_iso
from ..model import Drop, slug


def load(path: str) -> list[Drop]:
    try:
        with open(path) as f:
            rows = yaml.safe_load(f) or []
    except FileNotFoundError:
        return []
    drops = []
    for r in rows:
        start = parse_iso(str(r["start"])) if r.get("start") else None
        day = date.fromisoformat(str(r["date"])) if r.get("date") else None
        when = (start.isoformat() if start else str(day)) or "tbd"
        drops.append(Drop(
            id=f"manual:{slug(r['title'])}:{slug(when)}",
            game=r.get("game", "Other"),
            title=r["title"],
            url=r.get("url", ""),
            source=r.get("source", "manual"),
            kind=r.get("kind", "drop"),
            start=start, day=None if start else day,
            price=r.get("price"),
            note=r.get("note", ""),
            premium=bool(r.get("premium", False)),
            buy_url=r.get("buy_url"),
        ))
    return drops
