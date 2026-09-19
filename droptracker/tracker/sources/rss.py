"""Any RSS 2.0 / Atom feed (PokeBeach, shop blogs, news sites).
Keeps only items that mention a watched game AND pre-order/release wording."""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from ..classify import classify
from ..dates import parse_rfc822
from ..model import Drop

DEFAULT_KEYWORDS = r"pre-?orders?|release date|launch|drop|restock|pok[eé]mon center|costco|premium bandai|exclusive"
ATOM = "{http://www.w3.org/2005/Atom}"


def parse(xml_text: str, feed: dict, games: dict, watch: set) -> list[Drop]:
    kw = re.compile(feed.get("keywords") or DEFAULT_KEYWORDS, re.I)
    root = ET.fromstring(xml_text)
    entries = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    drops = []
    for e in entries:
        title = (e.findtext("title") or e.findtext(f"{ATOM}title") or "").strip()
        link = e.findtext("link") or ""
        if not link:
            l = e.find(f"{ATOM}link")
            link = l.get("href", "") if l is not None else ""
        blob = title + " " + (e.findtext("description") or e.findtext(f"{ATOM}summary") or "")
        if not kw.search(blob):
            continue
        game = feed.get("game") or classify(blob, games)
        if game is None or (watch and game not in watch):
            continue
        published = parse_rfc822(e.findtext("pubDate") or e.findtext(f"{ATOM}updated") or e.findtext(f"{ATOM}published"))
        key = hashlib.sha1(link.encode() or title.encode()).hexdigest()[:12]
        lottery = bool(re.search(r"lotter(y|ies)|raffle|chance to buy|zaiko|release event", blob, re.I))
        drops.append(Drop(
            id=f"rss:{feed['name']}:{key}",
            game=game, title=title, url=link.strip(), source=feed["name"],
            kind="lottery" if lottery else "news", day=published.date() if published else None,
            premium=lottery,
            note=feed.get("note", "") if lottery else "",
        ))
    return drops


def collect(session, feed: dict, games: dict, watch: set) -> list[Drop]:
    r = session.get(feed["url"], timeout=20)
    r.raise_for_status()
    return parse(r.text, feed, games, watch)
