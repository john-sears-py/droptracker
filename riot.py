"""Riftbound / Riot Merch Store drops.

Two public, crawler-allowed sources (both robots.txt: Allow /):

1. playriftbound.com/en-us/news/  - server-rendered. Riot announces every merch-store
   drop here ("Radiance Merch Store Update", "... Drawing FAQ"). Most are DRAWINGS:
   sign up in a window, winners emailed, 24h to check out. We read the article and
   pull the sign-up window ("Email Sign-Up Window: September 25-30, 9:00 AM PT") and
   the registration link, so the alert button goes straight to sign-up and you get a
   reminder before the window opens.

2. merch.riotgames.com/sitemap.xml - lists every product page (no dates). A new
   Riftbound product URL = a new product page went up.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..dates import MONTHS
from ..model import Drop

NEWS = "https://playriftbound.com/en-us/news/"
BASE = "https://playriftbound.com"
MERCH_SITEMAP = "https://merch.riotgames.com/sitemap.xml"
PT = ZoneInfo("America/Los_Angeles")

COMMERCE = re.compile(r"merch|store|drawing|pre-?orders?|bundle|lotter|sign-?up|registration|"
                      r"booster display|release event|chance to buy", re.I)
DRAWING = re.compile(r"drawing|lotter|sign-?up|registration", re.I)
_WINDOW = re.compile(
    r"Sign-?Up\s+Window\s*:?\s*([A-Za-z]+)\.?\s+(\d{1,2})"          # month day1
    r"(?:\s*[-–]\s*(?:([A-Za-z]+)\.?\s+)?(\d{1,2}))?"                 # - [month] day2
    r",?\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*([AP])\.?M\.?\s*(PT|PDT|PST)?", re.I)
_DRAW = re.compile(r"Drawing\s+Selection\s+Begins\s*:?\s*([A-Za-z]+)\.?\s+(\d{1,2})", re.I)


def parse_news(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select('a[href*="/news/"]'):
        t = a.select_one('[data-testid="card-title"]')
        if not t:
            continue
        href = a["href"]
        url = href if href.startswith("http") else BASE + href
        if url in seen:
            continue
        seen.add(url)
        tm = a.find("time")
        stamp = tm.get("datetime") or tm.get("dateTime") if tm else None
        cat = a.select_one('[data-testid="card-category"]')
        desc = a.select_one('[data-testid="card-description"]')
        out.append({
            "url": url,
            "title": t.get_text(" ", strip=True),
            "date": stamp[:10] if stamp else None,
            "category": cat.get_text(strip=True) if cat else "",
            "desc": desc.get_text(" ", strip=True) if desc else "",
        })
    return out


def _date(month: str, day: str, year: int) -> date | None:
    m = MONTHS.get(month.lower()[:4].rstrip(".")) or MONTHS.get(month.lower()[:3])
    try:
        return date(year, m, int(day)) if m else None
    except ValueError:
        return None


def parse_article(html: str, posted: date) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    reg = None
    for a in soup.select("a[href]"):
        h = a["href"]
        if re.search(r"/preorder/registration|merch\.riotgames\.com", h):
            reg = h if h.startswith("http") else BASE + h
            break
    info = {"register": reg, "opens": None, "closes": None, "drawing": None}
    m = _WINDOW.search(text)
    if m:
        mon1, d1, mon2, d2, hh, mm, ap, _ = m.groups()
        start_day = _date(mon1, d1, posted.year)
        if start_day and start_day < posted - timedelta(days=60):
            start_day = start_day.replace(year=posted.year + 1)
        if start_day:
            h = int(hh) % 12 + (12 if ap.upper() == "P" else 0)
            info["opens"] = datetime(start_day.year, start_day.month, start_day.day, h, int(mm or 0),
                                     tzinfo=PT).astimezone(timezone.utc).isoformat()
            if d2:
                end = _date(mon2 or mon1, d2, start_day.year)
                info["closes"] = end.isoformat() if end else None
    m = _DRAW.search(text)
    if m:
        dd = _date(m.group(1), m.group(2), posted.year)
        info["drawing"] = dd.isoformat() if dd else None
    return info


def news_drops(post: dict, info: dict | None) -> list[Drop]:
    posted = date.fromisoformat(post["date"]) if post.get("date") else None
    key = post["url"].rstrip("/").rsplit("/", 1)[-1]
    drawing = bool(DRAWING.search(post["title"] + " " + post["desc"])) or bool(info and info.get("opens"))
    info = info or {}
    buy = info.get("register") or post["url"]
    if info.get("opens"):
        opens = datetime.fromisoformat(info["opens"])
        bits = [f"Sign-up closes {info['closes']}" if info.get("closes") else "",
                f"drawing starts {info['drawing']}" if info.get("drawing") else "",
                "winners get 24h to check out; needs a Riot account and riotgames.com email not in spam"]
        out = [Drop(id=f"riot:{key}:opens", game="Riftbound", title=f"Riot drawing sign-up opens: {post['title']}",
                    url=post["url"], source="playriftbound.com", kind="lottery", start=opens,
                    note="; ".join(b for b in bits if b), premium=True, buy_url=buy)]
        if info.get("closes"):
            out.append(Drop(id=f"riot:{key}:closes", game="Riftbound",
                            title=f"LAST DAY to sign up: {post['title']}", url=post["url"],
                            source="playriftbound.com", kind="lottery",
                            day=date.fromisoformat(info["closes"]), premium=True, buy_url=buy))
        return out
    return [Drop(id=f"riot:{key}", game="Riftbound", title=post["title"], url=post["url"],
                 source="playriftbound.com", kind="lottery" if drawing else "news",
                 day=posted, note=post["desc"][:200], premium=drawing, buy_url=buy if drawing else None)]


def collect_news(session, state: dict, now: datetime, lookback_days: int = 10) -> list[Drop]:
    cache = state.setdefault("riot_articles", {})
    r = session.get(NEWS, timeout=20)
    r.raise_for_status()
    cutoff = (now - timedelta(days=lookback_days)).date()
    drops = []
    for post in parse_news(r.text):
        if not COMMERCE.search(post["title"] + " " + post["desc"]):
            continue
        if post["date"] and date.fromisoformat(post["date"]) < cutoff:
            continue
        info = cache.get(post["url"])
        if info is None:
            a = session.get(post["url"], timeout=20)
            a.raise_for_status()
            info = parse_article(a.text, date.fromisoformat(post["date"]) if post["date"] else now.date())
            cache[post["url"]] = info
        drops.extend(news_drops(post, info))
    return drops


def _merch_title(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    words = slug.replace("-", " ").split()
    return " ".join(w.upper() if w in ("t1", "tcg") else (w if w.isdigit() else w.capitalize()) for w in words)


def collect_merch(session, state: dict, now: datetime, lookback_days: int = 30) -> list[Drop]:
    st = state.setdefault("riot_merch", {"initialized": False, "first_seen": {}})
    r = session.get(MERCH_SITEMAP, timeout=20)
    r.raise_for_status()
    urls = [u.strip() for u in re.findall(r"<loc>([^<]+)</loc>", r.text)
            if "/product/" in u and "riftbound" in u.lower()]
    first = st["first_seen"]
    for u in urls:
        if u not in first:
            # Products already listed the first time we look are history, not drops.
            first[u] = None if not st["initialized"] else now.date().isoformat()
    st["initialized"] = True
    cutoff = (now - timedelta(days=lookback_days)).date().isoformat()
    drops = []
    for u in urls:
        seen = first.get(u)
        if not seen or seen < cutoff:
            continue
        link = u.replace("merch.riotgames.com/product/", "merch.riotgames.com/en-us/product/")
        drops.append(Drop(id="riotmerch:" + u.rstrip("/").rsplit("/", 1)[-1], game="Riftbound",
                          title="New on Riot Merch Store: " + _merch_title(u), url=link,
                          source="merch.riotgames.com", kind="drop", day=date.fromisoformat(seen),
                          note="New product page. Check whether it's first-come or a drawing.",
                          premium=True, buy_url=link))
    return drops
