# droptracker

Every card drop and pre-order in one calendar on your phone, with push alerts.

It checks six kinds of sources every 20 minutes:

| Source | What it catches |
|---|---|
| **Shopify card shops** (`config.yaml → shopify`) | New "pre-order" listings for Riftbound, One Piece, Pokémon, Topps, Magic — the moment a shop posts one |
| **Official One Piece site** | New products, **Premium Bandai** items flagged, and the "Pre-order Period" start date from each product page |
| **Premium Bandai USA sitemap** | New **"Chance to Buy" lotteries** (OP booster boxes, special sets) |
| **Bandai Namco US shop news (RSS)** | ONE PIECE Official Shop **release lotteries** (Zaiko), incl. Arlington Heights + Gurnee IL |
| **RSS feeds** (PokeBeach by default) | Pokémon pre-order / Pokémon Center / Costco announcements |
| **`drops.yaml`** (you edit) | Timed drops from sites that block scrapers — mainly Topps.com |

Output: a subscribable calendar (`drops.ics`), a dashboard page, and phone push alerts for anything new.

## Setup (about 10 minutes)

1. **Make a GitHub repo** and upload everything in this folder. It must be **public** for free GitHub Pages; nothing in it is private (alerts use secrets, below).
2. **Phone alerts:** install the **ntfy** app (iOS/Android), tap *Subscribe*, and make up a long, hard-to-guess topic name, e.g. `jack-drops-7f3k2q`. Anyone who knows the name can read it, so don't use something guessable.
3. In the repo: **Settings → Secrets and variables → Actions → New repository secret** → name `NTFY_TOPIC`, value = your topic name. (Optional: `DISCORD_WEBHOOK_URL` for a Discord channel too.)
4. **Settings → Pages →** Source: *Deploy from a branch*, Branch: `main`, folder: `/docs`. Save.
5. **Actions tab →** enable workflows → *track drops* → **Run workflow**. The first run is silent on purpose: it records everything that already exists, so you don't get 50 alerts at once. From then on, you're alerted only when something new appears.
6. **Subscribe the calendar:** your dashboard is at `https://<your-username>.github.io/<repo>/`. Copy the *subscribe to calendar* link (`…/drops.ics`):
   - **iPhone:** Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar → paste.
   - **Google Calendar (web):** Other calendars → + → From URL → paste. (Google refreshes subscribed calendars slowly, sometimes every 12–24h — rely on the ntfy push for anything urgent.)

## Everyday use

- **Add a shop:** run `python check_shop.py someshop.com` locally (or just add it). If it says *Shopify OK*, add it under `shopify:` in `config.yaml`. Local Chicago shops and the stores you actually buy from are the most valuable additions.
- **Add a Topps drop time:** Topps's release calendar lists times in UTC. Add an entry to `drops.yaml` with `start: 2026-10-15T16:00:00Z`. Chicago = UTC−5 until Nov 1, then UTC−6. You get a push ~60 min before and a calendar alert 15 min before.
- **Change which games alert:** edit `watch:` in `config.yaml`.
- **Manual check anytime:** Actions → *track drops* → Run workflow.

## Coverage map: what's caught and what isn't

### One Piece / Bandai (the three channels that matter)

| Channel | How it sells | Covered? | How / caveat |
|---|---|---|---|
| **Premium Bandai USA "Chance to Buy" lotteries** (booster boxes, special sets) | Online lottery: enter anytime in the window, winners emailed a purchase link | ✅ **Yes** | Watches PB's public content sitemap for new `/us/hotdeals/…` pages and reads the page title. Alert = **LOTTERY OPEN**, urgent. Caveat: the entry window is JavaScript-rendered, so open the page to see the deadline. The sitemap may refresh only every few hours; lotteries run for days, so that's fine. |
| **ONE PIECE CARD GAME Official Shops** (new-set release lotteries; IL shops: Arlington Heights, Gurnee) | In-store pickup lottery via Zaiko, announced on Bandai Namco's shop site | ✅ **Yes** | RSS feed of shop.bandainamco-am.com. Posts mentioning lottery/Zaiko/release event → LOTTERY alert. |
| **Premium Bandai items announced on the official OP site** (Premium Card Collections, Heroines sets, anniversary sets) | Pre-order period on PB | ✅ **Yes** | Official products page: flags PREMIUM BANDAI items, reads the "Pre-order Period" / "Pre-order starts on" date. |
| **Premium Bandai first-come pre-orders for items *not* on the official OP site** | Race: opens at a set time, sells out in minutes | ⚠️ **Partial** | PB product pages have no title in their raw HTML and the product sitemap is ~9 MB, so they aren't watched directly. Backup: a paid PB alert service (Autoqueue, ~$8/mo). PB US drops have tended to land ~7–9:30 pm Chicago. |
| Event-exclusive / in-person only (Bandai Card Games Fest, Pirates League prizes, TCG+ app events) | At events | ❌ No | Not sold online. The Bandai Namco shop feed catches Pirates League schedule posts only. |
| Japanese Premium Bandai (p-bandai.jp) | JP lotteries | ❌ No | Out of scope; your Japan proxy flow covers it. |

### Everything else

| Channel | Covered? | Notes |
|---|---|---|
| Shop pre-orders at Shopify card shops (Riftbound, One Piece, Pokémon, Magic) | ✅ | Only the shops listed in `config.yaml`. Add yours with `check_shop.py`. |
| Shops not on Shopify, or that announce only on Instagram/Discord | ❌ | Add a shop's RSS feed if it has one; otherwise not coverable. |
| Pokémon preorder *announcements* (Pokémon Center, Costco, etc.) | ✅ news-level | PokeBeach RSS. Actual restock/checkout timing → PokeNotify. |
| Topps.com drops | ⚠️ manual | Cloudflare bot check; add times to `drops.yaml`. EQL raffles likewise. |
| Posts that only appear on X | ❌ | Needs the paid X API. |

## What it deliberately doesn't do

- **X/Twitter:** scraping it breaks X's terms and gets blocked; the paid API is the only reliable route. Most X drop posts trace back to shop listings and official pages, which this watches directly.
- **Bot-protected or app-only pages (Topps.com, Pokémon Center, Costco, Premium Bandai's data API):** the tracker never tries to get around protection. Topps times go in `drops.yaml`; Pokémon Center/Costco are covered by the PokeBeach feed plus a service like PokeNotify; Premium Bandai is read only through its public sitemap and the official One Piece site.
- **Buying anything.** It alerts; you check out.

## Run locally

```bash
pip install -r requirements.txt
python run.py --dry-run      # prints what it would alert; changes nothing
python -m pytest -q          # 22 tests, no network needed
```

## Costs

GitHub Actions is free for public repos. ntfy.sh is free. Each run takes well under a minute.
