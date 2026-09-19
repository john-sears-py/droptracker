import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

import run
from tracker import notify, output
from tracker.classify import compile_games, is_preorder, classify
from tracker.dates import parse_month_day
from tracker.model import Drop
from tracker.sources import manual, onepiece, pbandai, riot, rss, shopify

FX = os.path.join(os.path.dirname(__file__), "fixtures")
NOW = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)
GAMES = compile_games(None)
WATCH = {"Riftbound", "One Piece", "Pokemon", "Topps", "Magic"}


def fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


# ---------- classify ----------
@pytest.mark.parametrize("title,tags,body,want", [
    ("Riftbound Radiance Booster Box Pre-Order", [], "", True),
    ("OP-18 Booster Box", "English, Pre-Order", "", True),
    ("Delta Reign ETB", [], "This item is a pre-order.", True),
    ("Blazing Scorcher", [], "We offer pre-order on many items, see policy.", False),  # generic policy text
    ("Pokemon Pre-Owned Binder", [], "", False),
    ("Topps Chrome Presale Box", [], "", True),
])
def test_is_preorder(title, tags, body, want):
    assert is_preorder(title, tags, body) is want


def test_classify_one_piece_by_code():
    assert classify("The Dominance of God Booster Box OP-18", GAMES) == "One Piece"
    assert classify("Bowman Chrome Hobby", GAMES) == "Topps"
    assert classify("Yugioh Glorious Victors", GAMES) is None


# ---------- dates ----------
def test_month_day_with_and_without_year():
    today = date(2026, 9, 19)
    assert parse_month_day("April 24, 2026 -", today) == date(2026, 4, 24)
    assert parse_month_day("October 13", today) == date(2026, 10, 13)
    assert parse_month_day("January 5", today) == date(2027, 1, 5)       # rolls into next year
    assert parse_month_day("Sept 2", today) == date(2026, 9, 2)           # recent past keeps year


# ---------- shopify ----------
def test_shopify_parse():
    products = json.loads(fx("shopify_products.json"))["products"]
    drops = shopify.parse(products, {"domain": "shop.test", "name": "Test Shop"}, GAMES, WATCH, NOW, 45)
    by = {d.id: d for d in drops}
    assert set(by) == {"shopify:shop.test:101", "shopify:shop.test:102", "shopify:shop.test:106"}
    rb = by["shopify:shop.test:101"]
    assert rb.game == "Riftbound" and rb.kind == "preorder" and rb.price == "$129.95"
    assert rb.url == "https://shop.test/products/riftbound-radiance-booster-box-pre-order"
    assert by["shopify:shop.test:102"].game == "One Piece"          # tags as a comma string
    assert by["shopify:shop.test:106"].game == "Pokemon"            # pre-order only in body


# ---------- one piece ----------
def test_onepiece_index_and_details():
    items = onepiece.parse_index(fx("op_index.html"))
    assert [i["title"] for i in items][0] == "Premium Card Collection -Ace & Sabo & Luffy-"
    assert items[0]["labels"] == ["PREMIUM BANDAI"] and items[1]["labels"] == []
    assert items[2]["url"] == "https://en.onepiece-cardgame.com/products/collection-drama002.html"

    det = onepiece.parse_detail(fx("op_detail_period.html"), NOW.date())
    assert det == {"preorder_day": "2026-04-24", "release_day": None, "delivery": "November 2026", "premium": True}
    d = onepiece.to_drop(items[2], det)
    assert d.kind == "preorder" and d.premium and d.title.startswith("[Premium Bandai]")
    assert "delivers November 2026" in d.note

    det2 = onepiece.parse_detail(fx("op_detail_starts.html"), NOW.date())
    assert det2["preorder_day"] == "2026-10-13"


def test_onepiece_nav_mention_is_not_premium():
    det = onepiece.parse_detail(fx("op_detail_plain.html"), NOW.date())
    assert det == {"preorder_day": None, "release_day": "2026-10-30", "delivery": "October 30, 2026", "premium": False}


def test_onepiece_release_without_preorder_is_release():
    item = {"url": "https://x/products/playmat.html", "title": "Playmat", "labels": [], "price": "USD $43.00"}
    d = onepiece.to_drop(item, {"preorder_day": None, "delivery": None, "premium": False})
    assert d.kind == "release" and d.day is None and not d.premium


# ---------- rss ----------
def test_rss_keeps_only_relevant():
    drops = rss.parse(fx("feed.xml"), {"name": "PokeBeach", "game": "Pokemon"}, GAMES, WATCH)
    assert len(drops) == 1 and drops[0].day == date(2026, 9, 17)
    assert "pre-orders" in drops[0].title.lower()


def test_rss_bandai_shop_lottery():
    feed = {"name": "BN", "keywords": r"one piece|\bOP-?\d{2}\b|lotter|zaiko|release event", "note": "IL shops"}
    drops = rss.parse(fx("bn_shops_feed.xml"), feed, GAMES, WATCH)
    assert len(drops) == 1                                   # the Gundam post is ignored
    d = drops[0]
    assert d.game == "One Piece" and d.kind == "lottery" and d.premium and d.note == "IL shops"


# ---------- premium bandai ----------
def test_pbandai_sitemap_and_titles():
    entries = pbandai.parse_sitemap(fx("pb_sitemap_content.xml"))
    urls = [u.rsplit("/", 1)[-1] for u, _ in entries]
    assert urls == ["chancetobuyop13", "doubledealcardsleeve", "op16", "op17"]   # index/past/specialfeature skipped
    t = pbandai.page_title(fx("pb_op16.html"))
    assert t == "Chance to Buy: ONE PIECE CARD GAME  -THE TIME OF BATTLE- [OP-16] Booster Box"
    d = pbandai.to_drop(entries[2][0], entries[2][1], t, GAMES)
    assert d.kind == "lottery" and d.game == "One Piece" and d.premium and d.day == date(2026, 9, 17)
    assert pbandai.to_drop(entries[1][0], entries[1][1], pbandai.page_title(fx("pb_sleeve.html")), GAMES) is None


def test_pbandai_collect_lookback_and_cache():
    state = {}
    s = FakeSession()
    drops = pbandai.collect(s, state, GAMES, WATCH, NOW, lookback_days=30)
    assert sorted(d.id for d in drops) == ["pbandai:op16", "pbandai:op17"]       # OP-13 (March) too old
    assert len(state["pbandai_titles"]) == 3                                  # op16, op17, sleeve cached
    calls = []
    s.get = lambda url, timeout=None, params=None: (calls.append(url), FakeSession.get(s, url, params, timeout))[1]
    pbandai.collect(s, state, GAMES, WATCH, NOW, lookback_days=30)
    assert calls == [pbandai.SITEMAP]                                         # titles served from cache


# ---------- manual ----------
def test_manual_file(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("- title: Bowman Chrome\n  game: Topps\n  start: 2026-09-23T16:00:00Z\n"
                 "- title: Chrome F1\n  game: Topps\n  date: 2026-10-15\n")
    a, b = manual.load(str(p))
    assert a.start == datetime(2026, 9, 23, 16, tzinfo=timezone.utc) and a.day is None
    assert b.day == date(2026, 10, 15) and b.start is None
    assert manual.load(str(tmp_path / "missing.yaml")) == []


# ---------- output ----------
def test_ics_is_valid_and_folded():
    long = "X" * 200
    drops = [
        Drop(id="a", game="Topps", title="Bowman Chrome, hobby; box", url="https://t", source="m",
             kind="drop", start=datetime(2026, 9, 23, 16, tzinfo=timezone.utc)),
        Drop(id="b", game="One Piece", title=long, url="https://o", source="s", kind="preorder",
             day=date(2026, 10, 13)),
    ]
    ics = output.to_ics(drops, NOW)
    lines = ics.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"
    assert all(len(l.encode()) <= 75 for l in lines)
    assert "DTSTART:20260923T160000Z" in ics and "TRIGGER:-PT15M" in ics
    assert "DTSTART;VALUE=DATE:20261013" in ics and "DTEND;VALUE=DATE:20261014" in ics
    assert "Bowman Chrome\\, hobby\\; box" in ics
    assert ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") == 2


def test_window_filters_old():
    old = Drop(id="o", game="G", title="old", url="", source="", kind="preorder", day=date(2026, 1, 1))
    new = Drop(id="n", game="G", title="new", url="", source="", kind="preorder", day=date(2026, 9, 20))
    assert [d.id for d in output.window([old, new], NOW)] == ["n"]


def test_due_reminders():
    soon = Drop(id="s", game="T", title="soon", url="", source="", kind="drop", start=NOW + timedelta(minutes=30))
    later = Drop(id="l", game="T", title="later", url="", source="", kind="drop", start=NOW + timedelta(hours=5))
    past = Drop(id="p", game="T", title="past", url="", source="", kind="drop", start=NOW - timedelta(minutes=5))
    assert [d.id for d in notify.due_reminders([soon, later, past], {}, NOW, 60)] == ["s"]
    assert notify.due_reminders([soon], {"s": "x"}, NOW, 60) == []


# ---------- end to end with a fake network ----------
class FakeResp:
    def __init__(self, text=None, js=None):
        self.text, self._js = text or "", js

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


class FakeSession:
    posts = []

    def __init__(self):
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        if url.endswith("/products.json"):
            data = json.loads(fx("shopify_products.json"))
            return FakeResp(js=data if (params or {}).get("page", 1) == 1 else {"products": []})
        if url == onepiece.INDEX:
            return FakeResp(fx("op_index.html"))
        if "collection-drama002" in url:
            return FakeResp(fx("op_detail_period.html"))
        if "card_collection_asl" in url:
            return FakeResp(fx("op_detail_starts.html"))
        if "onepiece-cardgame.com/products/" in url:
            return FakeResp(fx("op_detail_plain.html"))
        if url.endswith("/feed"):
            return FakeResp(fx("feed.xml"))
        if url == pbandai.SITEMAP:
            return FakeResp(fx("pb_sitemap_content.xml"))
        if url.endswith("/us/hotdeals/op16"):
            return FakeResp(fx("pb_op16.html"))
        if url.endswith("/us/hotdeals/op17"):
            return FakeResp(fx("pb_op17.html"))
        if "/us/hotdeals/" in url:
            return FakeResp(fx("pb_sleeve.html"))
        if url.endswith("bandainamco-am.com/feed/"):
            return FakeResp(fx("bn_shops_feed.xml"))
        if url == riot.NEWS:
            return FakeResp(fx("riot_news.html"))
        if url.endswith("/radiance-merch-store-update"):
            return FakeResp(fx("riot_article_radiance.html"))
        if url.startswith("https://playriftbound.com/en-us/news/"):
            return FakeResp(fx("riot_article_plain.html"))
        if url == riot.MERCH_SITEMAP:
            return FakeResp(fx("riot_merch_sitemap.xml"))
        raise AssertionError("unexpected url " + url)

    def post(self, url, data=None, headers=None, json=None, timeout=None):
        FakeSession.posts.append((url, headers, data))


def test_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(run.requests, "Session", FakeSession)
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    cfg = tmp_path / "config.yaml"
    drops_yaml = tmp_path / "drops.yaml"
    drops_yaml.write_text("- title: Future drop\n  game: Topps\n  date: 2099-01-01\n")
    cfg.write_text(
        "timezone: America/Chicago\nwatch: [Riftbound, One Piece, Pokemon, Topps]\n"
        "shopify:\n  - domain: shop.test\n    name: Test\npause_seconds: 0\nlookback_days: 45\n"
        "rss:\n  - name: PB\n    url: https://pb.test/feed\n    game: Pokemon\n"
        f"manual_file: {drops_yaml}\n")
    # Freeze "now" so the fixture dates are inside the lookback window.
    class FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(run, "datetime", FrozenDT)

    args = ["--config", str(cfg), "--state", str(tmp_path / "state.json"), "--out", str(tmp_path / "docs")]
    FakeSession.posts = []
    assert run.main(args) == 0
    assert FakeSession.posts == []                     # first run is silent (bootstrap)
    state = json.loads((tmp_path / "state.json").read_text())
    assert "shopify:shop.test:101" in state["seen"]
    out = json.loads((tmp_path / "docs" / "drops.json").read_text())
    assert out["errors"] == []
    ics = (tmp_path / "docs" / "drops.ics").read_text()
    assert "Riftbound Radiance Booster Box Pre-Order" in ics
    assert "[Premium Bandai]" in ics

    # Second run: nothing new -> no alerts. Then a new listing appears -> exactly one alert.
    assert run.main(args) == 0 and FakeSession.posts == []
    extra = json.loads(fx("shopify_products.json"))
    extra["products"].append({"id": 999, "title": "Riftbound Radiance Case Pre-Order", "handle": "case",
                              "published_at": "2026-09-19T08:00:00-05:00", "tags": [],
                              "variants": [{"price": "780.00", "available": True}]})
    orig_get = FakeSession.get
    monkeypatch.setattr(FakeSession, "get", lambda self, url, params=None, timeout=None:
                        FakeResp(js=extra) if url.endswith("/products.json") and (params or {}).get("page", 1) == 1
                        else orig_get(self, url, params, timeout))
    assert run.main(args) == 0
    assert len(FakeSession.posts) == 1
    url, headers, body = FakeSession.posts[0]
    assert url == "https://ntfy.sh/test-topic"
    assert b"Riftbound Radiance Case Pre-Order" in headers["Title"]
    assert headers["Priority"] == "high"


def test_new_pbandai_lottery_fires_one_urgent_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(run.requests, "Session", FakeSession)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    empty = tmp_path / "drops.yaml"
    empty.write_text("[]\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("watch: [One Piece]\nonepiece_official: false\npremium_bandai_us: true\n"
                   f"manual_file: {empty}\n")

    class FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(run, "datetime", FrozenDT)
    args = ["--config", str(cfg), "--state", str(tmp_path / "s.json"), "--out", str(tmp_path / "o")]
    FakeSession.posts = []
    run.main(args)                                  # bootstrap: silent
    assert FakeSession.posts == []

    xml = fx("pb_sitemap_content.xml").replace(
        "</urlset>", "<url><loc>https://p-bandai.com/us/hotdeals/op18</loc><lastmod>2026-09-19</lastmod></url></urlset>")
    orig = FakeSession.get

    def get(self, url, params=None, timeout=None):
        if url == pbandai.SITEMAP:
            return FakeResp(xml)
        if url.endswith("/us/hotdeals/op18"):
            return FakeResp("<title>Chance to Buy: ONE PIECE CARD GAME -THE DOMINANCE OF GOD- [OP-18] Booster Box | PREMIUM BANDAI USA</title>")
        return orig(self, url, params, timeout)
    monkeypatch.setattr(FakeSession, "get", get)
    run.main(args)
    assert len(FakeSession.posts) == 1
    _, headers, _ = FakeSession.posts[0]
    assert b"LOTTERY OPEN" in headers["Title"] and b"OP-18" in headers["Title"]
    assert headers["Priority"] == "urgent" and headers["Tags"] == "ticket"


# ---------- buy links on alerts ----------
class Capture:
    def __init__(self):
        self.posts = []

    def post(self, url, data=None, headers=None, json=None, timeout=None):
        self.posts.append((url, headers, data, json))


def test_alert_has_buy_button_click_and_link(monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    s = Capture()
    d = Drop(id="x", game="One Piece", title="Premium Card Collection", source="onepiece-cardgame.com",
             url="https://en.onepiece-cardgame.com/products/x.html", kind="preorder", day=date(2026, 10, 13),
             premium=True, buy_url="https://p-bandai.com/us/brand/onepiececardgame")
    notify.new_drop(s, d, ZoneInfo("America/Chicago"), "https://me.github.io/droptracker/")
    _, h, body, _ = s.posts[0]
    assert h["Click"] == "https://p-bandai.com/us/brand/onepiececardgame"          # tap = buy page
    assert h["Actions"] == ("view, Pre-order now, https://p-bandai.com/us/brand/onepiececardgame, clear=true; "
                            "view, Details, https://en.onepiece-cardgame.com/products/x.html, clear=true; "
                            "view, Dashboard, https://me.github.io/droptracker/, clear=true")
    assert body.decode().endswith("https://p-bandai.com/us/brand/onepiececardgame")  # link in text too


def test_lottery_button_and_discord_link(monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    s = Capture()
    d = pbandai.to_drop("https://p-bandai.com/us/hotdeals/op18", date(2026, 9, 19),
                        "Chance to Buy: ONE PIECE CARD GAME [OP-18] Booster Box", GAMES)
    notify.new_drop(s, d, ZoneInfo("America/Chicago"))
    assert pbandai.to_drop is not None and d.buy_url == d.url
    assert "https://p-bandai.com/us/hotdeals/op18" in s.posts[0][3]["content"]
    assert notify._actions([("Enter lottery", d.url), ("A, b; c", "https://z")]) == \
        "view, Enter lottery, https://p-bandai.com/us/hotdeals/op18, clear=true; view, A  b  c, https://z, clear=true"


# ---------- riftbound / riot ----------
def test_riot_news_parse():
    posts = riot.parse_news(fx("riot_news.html"))
    assert [p["title"] for p in posts][:2] == ["Radiance Preview Season", "Radiance Merch Store Update"]
    assert posts[1]["date"] == "2026-09-17" and posts[1]["category"] == "Announcements"
    assert posts[1]["url"] == "https://playriftbound.com/en-us/news/announcements/radiance-merch-store-update"


def test_riot_article_window_to_exact_times():
    info = riot.parse_article(fx("riot_article_radiance.html"), date(2026, 9, 17))
    assert info == {"register": "https://playriftbound.com/en-us/preorder/registration/",
                    "opens": "2026-09-25T16:00:00+00:00",          # 9:00 AM PDT
                    "closes": "2026-09-30", "drawing": "2026-10-05"}
    post = {"url": "https://playriftbound.com/en-us/news/announcements/radiance-merch-store-update",
            "title": "Radiance Merch Store Update", "date": "2026-09-17", "desc": ""}
    opens, closes = riot.news_drops(post, info)
    assert opens.kind == "lottery" and opens.start == datetime(2026, 9, 25, 16, tzinfo=timezone.utc)
    assert opens.buy_url == "https://playriftbound.com/en-us/preorder/registration/"
    assert "drawing starts 2026-10-05" in opens.note
    assert closes.day == date(2026, 9, 30) and closes.title.startswith("LAST DAY")


def test_riot_collect_news_filters_and_caches():
    state, s = {}, FakeSession()
    drops = riot.collect_news(s, state, NOW, lookback_days=10)
    ids = sorted(d.id for d in drops)
    # Radiance drawing (open + close) and Secret Garden bundle; not previews, organized play, or the Sept 3 post
    assert ids == ["riot:radiance-merch-store-update:closes", "riot:radiance-merch-store-update:opens",
                   "riot:secret-garden-bundle-events"]
    sg = [d for d in drops if d.id == "riot:secret-garden-bundle-events"][0]
    assert sg.kind == "news" and sg.day == date(2026, 9, 11)
    calls = []
    s.get = lambda url, timeout=None, params=None: (calls.append(url), FakeSession.get(s, url, params, timeout))[1]
    riot.collect_news(s, state, NOW, lookback_days=10)
    assert calls == [riot.NEWS]                                        # articles cached


def test_riot_merch_new_product_after_first_look():
    state, s = {}, FakeSession()
    assert riot.collect_merch(s, state, NOW) == []                    # existing products are history
    xml = fx("riot_merch_sitemap.xml").replace("</urlset>",
        "<url><loc>https://merch.riotgames.com/product/riftbound-radiance-booster-display/</loc></url></urlset>")
    s.get = lambda url, timeout=None, params=None: FakeResp(xml)
    (d,) = riot.collect_merch(s, state, NOW)
    assert d.title == "New on Riot Merch Store: Riftbound Radiance Booster Display"
    assert d.buy_url == "https://merch.riotgames.com/en-us/product/riftbound-radiance-booster-display/"
    assert d.day == NOW.date() and d.kind == "drop"
