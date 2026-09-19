"""Shopify stores: every store publishes /products.json, so a new pre-order
listing shows up here within minutes of the shop posting it.

This is the answer to "Riftbound/One Piece preorders open at a hundred shops at
a hundred different times" - watch the shops, not the announcements."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from ..classify import classify, is_preorder
from ..dates import parse_iso
from ..model import Drop


def fetch(session, domain: str, max_pages: int = 4, pause: float = 1.0) -> list:
    """Newest products first. Most shops' recent pre-orders are on page 1."""
    out = []
    for page in range(1, max_pages + 1):
        r = session.get(f"https://{domain}/products.json",
                        params={"limit": 250, "page": page}, timeout=20)
        r.raise_for_status()
        batch = r.json().get("products", [])
        out.extend(batch)
        if len(batch) < 250:
            break
        time.sleep(pause)
    return out


def _tags(p) -> list:
    t = p.get("tags") or []
    return [x.strip() for x in t.split(",")] if isinstance(t, str) else list(t)


def parse(products: list, shop: dict, games: dict, watch: set,
          now: datetime, lookback_days: int = 45) -> list[Drop]:
    domain = shop["domain"]
    cutoff = now - timedelta(days=lookback_days)
    drops = []
    for p in products:
        title = p.get("title", "")
        tags = _tags(p)
        if not is_preorder(title, tags, p.get("body_html") or ""):
            continue
        game = classify(" ".join([title, p.get("product_type") or "", " ".join(tags)]), games)
        if game is None or (watch and game not in watch):
            continue
        published = parse_iso(p.get("published_at")) or parse_iso(p.get("created_at"))
        if published and published < cutoff:
            continue        # an old pre-order the shop never cleaned up
        variants = p.get("variants") or []
        prices = [float(v["price"]) for v in variants if v.get("price")]
        in_stock = any(v.get("available") for v in variants)
        drops.append(Drop(
            id=f"shopify:{domain}:{p.get('id') or p.get('handle')}",
            game=game,
            title=title,
            url=f"https://{domain}/products/{p.get('handle')}",
            source=shop.get("name") or domain,
            kind="preorder",
            day=(published or now).astimezone(timezone.utc).date(),
            price=f"${min(prices):,.2f}" if prices else None,
            note="open" if in_stock else "listed, not purchasable yet (or sold out)",
            tags=tags[:8],
        ))
    return drops
