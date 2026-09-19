"""Test whether a shop can be tracked:  python check_shop.py someshop.com

Prints whether it's Shopify and which current listings the tracker would flag."""
import sys
from datetime import datetime, timezone

import requests
import yaml

from tracker.classify import compile_games
from tracker.sources import shopify

domain = sys.argv[1].replace("https://", "").replace("http://", "").strip("/")
cfg = yaml.safe_load(open("config.yaml"))
s = requests.Session()
s.headers["User-Agent"] = cfg.get("user_agent", "droptracker/1.0")
try:
    products = shopify.fetch(s, domain, max_pages=1)
except Exception as e:
    sys.exit(f"{domain}: not trackable as Shopify ({e})")
games = compile_games(cfg.get("games"))
drops = shopify.parse(products, {"domain": domain}, games, set(cfg.get("watch") or []),
                      datetime.now(timezone.utc), cfg.get("lookback_days", 45))
print(f"{domain}: Shopify OK, {len(products)} products on page 1, {len(drops)} pre-orders the tracker would flag:")
for d in drops:
    print(f"  [{d.game}] {d.title}  {d.price or ''}  ({d.note})")
print("\nAdd it to config.yaml under `shopify:` to start watching.")
