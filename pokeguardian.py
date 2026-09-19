"""PokeGuardian (pokeguardian.com) - Pokemon TCG product news, English and Japanese.

Replaces PokeBeach (blocks cloud servers) and Pokemon Center (bot-protected; not
touched). Homepage is server-rendered (JouwWeb): 24 newest posts, each an
<article class="jw-news-post"> with title, date ("15 Sept 2026") and a lead line.

This is the "what's coming and when" signal: set reveals, Pokemon Center /
store promos, merchandise waves, release dates. Actual shop pre-orders are caught
by the Shopify watcher; Pokemon Center checkout timing needs PokeNotify.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from ..dates import MONTHS
from ..model import Drop

BASE = "https://www.pokeguardian.com"

# Posts worth an alert. Deck lists / gameplay posts are skipped.
PRODUCT = re.compile(r"reveal|release|launch|pre-?order|pok[eé]mon center|costco|elite trainer|"
                     r"\betb\b|premium|collection|exclusive|promo|booster|box|tin|merch|restock|bundle|"
                     r"set list|special set|lottery|campaign", re.I)
HOT = re.compile(r"pok[eé]mon center|pre-?order|costco|elite trainer|\betb\b|exclusive|lottery|"
                 r"premium collection|ultra[- ]premium|restock", re.I)
_DMY = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})")


def parse_dmy(s: str) -> date | None:
    m = _DMY.search(s or "")
    if not m:
        return None
    mon = MONTHS.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower()[:4]) or MONTHS.get(m.group(2).lower()[:3])
    try:
        return date(int(m.group(3)), mon, int(m.group(1))) if mon else None
    except ValueError:
        return None


def parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article.jw-news-post"):
        a = art.select_one(".jw-news-post__title a[href]")
        if not a:
            continue
        href = a["href"]
        d = art.select_one(".jw-news-date")
        lead = art.select_one(".jw-news-post__lead")
        out.append({
            "url": href if href.startswith("http") else BASE + href,
            "title": a.get_text(" ", strip=True),
            "date": parse_dmy(d.get_text(" ", strip=True)) if d else None,
            "lead": lead.get_text(" ", strip=True) if lead else "",
        })
    return out


def to_drop(post: dict) -> Drop | None:
    blob = post["title"] + " " + post["lead"]
    if not PRODUCT.search(blob):
        return None
    key = post["url"].rstrip("/").rsplit("/", 1)[-1].split("_", 1)[0]    # numeric post id
    hot = bool(HOT.search(blob))
    return Drop(
        id=f"pokeguardian:{key}",
        game="Pokemon",
        title=post["title"],
        url=post["url"],
        source="PokeGuardian",
        kind="preorder" if re.search(r"pre-?order", blob, re.I) else "news",
        day=post["date"],
        note=post["lead"][:220],
        premium=hot,
    )


def collect(session, now: datetime, lookback_days: int = 10) -> list[Drop]:
    r = session.get(BASE + "/", timeout=20)
    r.raise_for_status()
    cutoff = (now - timedelta(days=lookback_days)).date()
    drops = []
    for post in parse(r.text):
        if post["date"] and post["date"] < cutoff:
            continue
        d = to_drop(post)
        if d:
            drops.append(d)
    return drops
