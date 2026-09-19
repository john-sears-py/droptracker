"""One pass: collect every source, alert on anything new or changed, write the
calendar feed and dashboard data. Designed to run every ~20 min on GitHub Actions.

    python run.py                 # normal run
    python run.py --dry-run       # no alerts sent, prints what would be sent
    python run.py --notify-initial  # first run normally stays silent; this alerts on everything
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import yaml

from tracker import notify, output
from tracker.classify import compile_games
from tracker.sources import manual, onepiece, pbandai, riot, rss, shopify


def load_state(path):
    try:
        with open(path) as f:
            s = json.load(f)
    except FileNotFoundError:
        s = {}
    s.setdefault("seen", {})
    s.setdefault("reminded", {})
    s.setdefault("onepiece_detail", {})
    return s


def signature(d) -> str:
    return f"{d.kind}|{d.start.isoformat() if d.start else d.day}"


def collect_all(cfg, session, state, now):
    games = compile_games(cfg.get("games"))
    watch = set(cfg.get("watch") or games.keys())
    drops, errors = [], []

    def attempt(name, fn):
        try:
            got = fn()
            drops.extend(got)
            print(f"  {name}: {len(got)}")
        except Exception as e:            # one broken source never kills the run
            errors.append(f"{name}: {type(e).__name__}: {e}"[:300])
            print(f"  {name}: ERROR {e}", file=sys.stderr)

    for shop in cfg.get("shopify", []):
        attempt(f"shopify {shop['domain']}", lambda shop=shop: shopify.parse(
            shopify.fetch(session, shop["domain"], cfg.get("shopify_pages", 2)),
            shop, games, watch, now, cfg.get("lookback_days", 45)))
        time.sleep(cfg.get("pause_seconds", 1.0))

    if cfg.get("onepiece_official", True) and (not watch or "One Piece" in watch):
        attempt("onepiece official", lambda: onepiece.collect(session, state, now))

    if cfg.get("premium_bandai_us", True):
        attempt("premium bandai US", lambda: pbandai.collect(
            session, state, games, watch, now, cfg.get("pbandai_lookback_days", 30)))

    if cfg.get("riot_riftbound", True) and (not watch or "Riftbound" in watch):
        attempt("riftbound news (Riot drawings)", lambda: riot.collect_news(
            session, state, now, cfg.get("riot_lookback_days", 10)))
        attempt("riot merch store", lambda: riot.collect_merch(session, state, now))

    for feed in cfg.get("rss", []):
        attempt(f"rss {feed['name']}", lambda feed=feed: rss.collect(session, feed, games, watch))

    attempt("manual drops.yaml", lambda: manual.load(cfg.get("manual_file", "drops.yaml")))

    uniq = {}
    for d in drops:
        uniq.setdefault(d.id, d)
    return list(uniq.values()), errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--state", default="state.json")
    ap.add_argument("--out", default="docs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notify-initial", action="store_true")
    a = ap.parse_args(argv)

    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    tz = ZoneInfo(cfg.get("timezone", "America/Chicago"))
    now = datetime.now(timezone.utc)
    state = load_state(a.state)
    bootstrap = not state["seen"] and not a.notify_initial

    session = requests.Session()
    session.headers["User-Agent"] = cfg.get("user_agent", "droptracker/1.0 (personal hobby release tracker)")

    print("collecting:")
    drops, errors = collect_all(cfg, session, state, now)

    alert_session = session if not a.dry_run else None
    sent = 0
    for d in drops:
        prev = state["seen"].get(d.id)
        sig = signature(d)
        if prev is None or prev.get("sig") != sig:
            is_update = prev is not None
            state["seen"][d.id] = {"first": (prev or {}).get("first", now.isoformat()), "sig": sig}
            if bootstrap or (d.kind == "news" and is_update):
                continue
            if a.dry_run or alert_session is None:
                print(f"  [would alert] {'UPDATED ' if is_update else ''}{d.game}: {d.title}")
            else:
                notify.new_drop(alert_session, d, tz, cfg.get("dashboard_url"))
            sent += 1

    for d in notify.due_reminders(drops, state["reminded"], now, cfg.get("reminder_lead_minutes", 60)):
        state["reminded"][d.id] = now.isoformat()
        if a.dry_run:
            print(f"  [would remind] {d.title} at {d.start.astimezone(tz)}")
        else:
            notify.reminder(session, d, tz, now, cfg.get("dashboard_url"))

    # keep state small
    cutoff = (now - timedelta(days=120)).isoformat()
    state["seen"] = {k: v for k, v in state["seen"].items() if v["first"] >= cutoff or k.startswith("manual:")}
    state["reminded"] = {k: v for k, v in state["reminded"].items() if v >= cutoff}

    shown = output.window(drops, now)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "drops.ics"), "w", newline="") as f:
        f.write(output.to_ics(shown, now, cfg.get("alarm_minutes", 15)))
    payload = json.loads(output.to_json(shown, now))
    payload["errors"] = errors
    payload["timezone"] = str(tz)
    with open(os.path.join(a.out, "drops.json"), "w") as f:
        json.dump(payload, f, indent=1)
    if not a.dry_run:                     # a dry run never marks anything as seen
        with open(a.state, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)

    print(f"done: {len(drops)} items, {sent} {'new (bootstrap, silent)' if bootstrap else 'alerts'}, "
          f"{len(errors)} source errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
