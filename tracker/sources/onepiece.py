"""Official One Piece Card Game site (English). Server-rendered, so plain HTML parsing works.

The products index tags Premium Bandai items; each product page carries a
'Pre-order Period: <date> -' banner (or 'Pre-order starts on <date>!' text)
and a 'Delivery Month'. That is the Premium Bandai signal - p-bandai.com itself
renders with JavaScript and is not worth scraping."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ..dates import parse_month_day
from ..model import Drop

BASE = "https://en.onepiece-cardgame.com"
INDEX = BASE + "/products/index.php"
PB_ONE_PIECE = "https://p-bandai.com/us/brand/onepiececardgame"

_PERIOD = re.compile(r"Pre-?order\s+Period\s*[:：]\s*(.+?)(?:-|–|$)", re.I)
_PB_BUY = re.compile(r"Apply through the Premium Bandai page|Where to buy\s*:?\s*PREMIUM BANDAI", re.I)
_STARTS = re.compile(r"Pre-?order\s+starts?\s+on\s+([A-Za-z]+\.?\s+\d{1,2}(?:,\s*\d{4})?)", re.I)


def parse_index(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for li in soup.select("li.linkListColBox"):
        a = li.select_one("a[href]")
        title = li.select_one(".linkListColTitle")
        if not a or not title:
            continue
        href = a["href"]
        cat = li.select_one(".linkListColCat")
        price = li.select_one(".linkListColPrice .data")
        items.append({
            "url": href if href.startswith("http") else BASE + href,
            "title": title.get_text(" ", strip=True),
            "category": cat.get_text(strip=True) if cat else li.get("data-cat", ""),
            "labels": [t.get_text(strip=True) for t in li.select(".linkListColTag")],
            "price": price.get_text(strip=True) if price else None,
        })
    return items


def parse_detail(html: str, today: date) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for dl in soup.select("dl"):
        dt, dd = dl.find("dt"), dl.find("dd")
        if dt and dd:
            fields[dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
    text = soup.get_text(" ", strip=True)
    preorder_day = None
    m = _PERIOD.search(text)
    if m:
        preorder_day = parse_month_day(m.group(1), today)
    if not preorder_day:
        m = _STARTS.search(text)
        if m:
            preorder_day = parse_month_day(m.group(1), today)
    # Only the purchase banner counts - "PREMIUM BANDAI" can appear in shared
    # site navigation on every product page.
    premium = bool(soup.select_one('img[alt="PREMIUM BANDAI"]')) or bool(_PB_BUY.search(text))
    delivery = fields.get("Delivery Month") or fields.get("Release Date")
    release_day = parse_month_day(delivery, today) if delivery else None   # None for "November 2026"
    return {
        "preorder_day": preorder_day.isoformat() if preorder_day else None,
        "release_day": release_day.isoformat() if release_day else None,
        "delivery": delivery,
        "premium": premium,
    }


def collect(session, state: dict, now: datetime, refresh_hours: int = 12,
            max_details: int = 15) -> list[Drop]:
    """Fetch the index every run; fetch a product page only when it's new or stale."""
    cache = state.setdefault("onepiece_detail", {})
    r = session.get(INDEX, timeout=20)
    r.raise_for_status()
    items = parse_index(r.text)
    fetched = 0
    drops = []
    for it in items:
        c = cache.get(it["url"])
        stale = (not c) or (now - datetime.fromisoformat(c["checked"]) > timedelta(hours=refresh_hours))
        if stale and fetched < max_details:
            d = session.get(it["url"], timeout=20)
            d.raise_for_status()
            c = {"checked": now.isoformat(), **parse_detail(d.text, now.date())}
            cache[it["url"]] = c
            fetched += 1
        drops.append(to_drop(it, c or {}))
    return drops


def to_drop(item: dict, detail: dict) -> Drop:
    premium = detail.get("premium") or any("PREMIUM BANDAI" in l.upper() for l in item["labels"])
    pre = detail.get("preorder_day")
    rel = detail.get("release_day")
    note_bits = []
    if detail.get("delivery"):
        note_bits.append(f"delivers {detail['delivery']}")
    if premium:
        note_bits.append("order via Premium Bandai USA (p-bandai.com/us)")
    return Drop(
        id="onepiece:" + item["url"].rsplit("/", 1)[-1],
        game="One Piece",
        title=("[Premium Bandai] " if premium else "") + item["title"],
        url=item["url"],
        source="onepiece-cardgame.com",
        kind="preorder" if pre else "release",
        day=date.fromisoformat(pre) if pre else (date.fromisoformat(rel) if rel else None),
        price=item.get("price"),
        note="; ".join(note_bits),
        premium=premium,
        # The official page only describes the product; Premium Bandai is where you order it.
        buy_url=PB_ONE_PIECE if premium else None,
    )
