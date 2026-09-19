"""Premium Bandai USA "Chance to Buy" lotteries and hot-deal pages.

p-bandai.com renders with JavaScript and its data API refuses requests that
don't come from its own app, so we don't touch the API. Instead we read the
public sitemap that robots.txt advertises for crawlers:

    https://p-bandai.com/us/sitemap-content_1.xml   (small; lists /us/hotdeals/* with <lastmod>)

A new hotdeals URL (or a fresh <lastmod> on an old one) = a new lottery/deal.
The page <title> is in the raw HTML, e.g.
    "Chance to Buy: ONE PIECE CARD GAME -THE TIME OF BATTLE- [OP-16] Booster Box | PREMIUM BANDAI USA ..."
The entry window itself is rendered by JavaScript, so the alert links to the page.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..classify import classify
from ..model import Drop

SITEMAP = "https://p-bandai.com/us/sitemap-content_1.xml"
_URL = re.compile(r"<url>\s*<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", re.S)
_TITLE = re.compile(r"<title>([^<]*)</title>", re.I)
_SKIP = re.compile(r"/us/hotdeals/?$|/us/hotdeals/past/?$")
_SUFFIX = re.compile(r"\s*\|\s*PREMIUM BANDAI USA.*$", re.I)

NOTE = ("Premium Bandai lottery: enter anytime in the window (odds are the same), winners get an "
        "emailed purchase link. Needs a p-bandai.com account with saved address + payment. "
        "Entry window is on the page. PB US drops have tended to land ~7-9:30 pm Chicago.")


def parse_sitemap(xml: str) -> list[tuple[str, date]]:
    out = []
    for loc, lastmod in _URL.findall(xml):
        loc = loc.strip()
        if "/us/hotdeals/" not in loc + "/" or _SKIP.search(loc):
            continue
        try:
            out.append((loc, date.fromisoformat(lastmod.strip()[:10])))
        except ValueError:
            continue
    return out


def page_title(html: str) -> str:
    m = _TITLE.search(html or "")
    return _SUFFIX.sub("", m.group(1)).strip() if m else ""


def to_drop(url: str, lastmod: date, title: str, games: dict) -> Drop | None:
    game = classify(title, games)
    if game is None:
        return None
    lottery = bool(re.search(r"chance to buy|lottery|raffle", title + " " + url, re.I))
    return Drop(
        id="pbandai:" + url.rstrip("/").rsplit("/", 1)[-1],
        game=game,
        title=("[Premium Bandai] " + re.sub(r"^Chance to Buy:\s*", "Chance to Buy: ", title)),
        url=url,
        source="p-bandai.com (US)",
        kind="lottery" if lottery else "drop",
        day=lastmod,
        note=NOTE if lottery else "Premium Bandai hot deal / limited sale. Check the page for timing.",
        premium=True,
    )


def collect(session, state: dict, games: dict, watch: set, now: datetime,
            lookback_days: int = 30, max_titles: int = 10) -> list[Drop]:
    cache = state.setdefault("pbandai_titles", {})
    r = session.get(SITEMAP, timeout=20)
    r.raise_for_status()
    cutoff = (now - timedelta(days=lookback_days)).date()
    drops, fetched = [], 0
    for url, lastmod in parse_sitemap(r.text):
        if lastmod < cutoff:
            continue                          # old pages stay quiet
        key = f"{url}|{lastmod.isoformat()}"  # re-fetch the title when a page is re-used
        title = cache.get(key)
        if title is None:
            if fetched >= max_titles:
                continue
            p = session.get(url, timeout=20)
            p.raise_for_status()
            title = page_title(p.text)
            cache[key] = title
            fetched += 1
        d = to_drop(url, lastmod, title, games)
        if d and (not watch or d.game in watch):
            drops.append(d)
    # keep the cache from growing forever
    for k in [k for k in cache if k.split("|")[-1] < cutoff.isoformat()]:
        del cache[k]
    return drops
