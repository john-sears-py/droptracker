"""The one shape every source produces."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Optional


@dataclass
class Drop:
    id: str                         # stable across runs: "<source>:<key>"
    game: str                       # "Riftbound", "One Piece", "Pokemon", "Topps", ...
    title: str
    url: str
    source: str                     # human-readable: "tierzerogames.com", "onepiece-cardgame.com"
    kind: str                       # "preorder" | "release" | "drop" | "news"
    start: Optional[datetime] = None    # exact moment (tz-aware) when known
    day: Optional[date] = None          # date only, when that's all we know
    price: Optional[str] = None
    note: str = ""
    premium: bool = False           # Premium Bandai, PC-exclusive, online-exclusive, etc.
    tags: list = field(default_factory=list)
    buy_url: Optional[str] = None   # where you actually buy / enter, when it differs from `url`

    def action_url(self) -> str:
        return self.buy_url or self.url

    def when(self) -> Optional[date]:
        if self.start:
            return self.start.date()
        return self.day

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.astimezone(timezone.utc).isoformat() if self.start else None
        d["day"] = self.day.isoformat() if self.day else None
        return d


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]
