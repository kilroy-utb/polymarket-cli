# Polymarket CLI

Read-only CLI for Polymarket's three public APIs.

- **Gamma API** — events, markets, search, metadata
- **CLOB API** — real-time prices, orderbook, price history
- **Data API** — recent trades, open interest

No authentication. No wallet. No signing. Read-only by design.

## Setup

```bash
cd /opt/data/polymarket-cli
chmod +x polymarket.py
# Optional: add to PATH
ln -sf "$(pwd)/polymarket.py" /usr/local/bin/polymarket
```

Requires Python 3.10+. No third-party dependencies — stdlib only (`urllib`, `json`, `argparse`).

## Commands

### Discovery (Gamma API)

| Command | What it does |
| --- | --- |
| `search "bitcoin"` | Search events/markets by query |
| `trending --limit 20` | Top events by volume |
| `market <slug>` | Single market by slug, includes conditionId + clobTokenIds |
| `event <slug>` | Single event with all its markets |

### Prices & orderbook (CLOB API)

| Command | What it does |
| --- | --- |
| `price <token_id>` | Current buy/sell price (use `--side sell` for sell) |
| `book <token_id>` | Full orderbook, top N levels (`--depth`) |
| `history <condition_id>` | Historical prices (`--interval 1d\|1w\|1m\|3m\|6m\|1y\|all`, `--fidelity`) |
| `token <token_id>` | One-shot snapshot: buy/sell/mid/spread/best bid/best ask |
| `quick <market_slug>` | Market + both token prices + both books in one command |

### Trades (Data API)

| Command | What it does |
| --- | --- |
| `trades --limit 50` | Recent trades across all markets |
| `trades --market <condition_id>` | Trades for one market |
| `trades --outcome Yes\|No` | Filter by outcome |

## Global flag

`--json` works on every command — emits JSON to stdout for piping:

```bash
polymarket search "fed rate" --json | jq '.events[0].title'
polymarket market <slug> --json | jq '.clobTokenIds'
polymarket token <token_id> --json | jq '{buy, sell, mid, spread}'
```

## Typical workflows

### "Find a market and look at it"

```bash
# 1. Search
polymarket search "trump 2028"

# 2. Pick a slug from results, get full market data
polymarket market will-donald-trump-win-the-2028-republican-presidential-nomination-687

# 3. One-shot snapshot of both sides (price + book)
polymarket quick will-donald-trump-win-the-2028-republican-presidential-nomination-687 --depth 5
```

### "Watch a specific token"

```bash
# Get token_id from `market` command output
polymarket token 16040015440196279900485035793550429453516625694844857319147506590755961451627 --depth 5

# Price history for the market
polymarket history 0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422 --interval 1w --fidelity 100

# Recent trades filtered to Yes
polymarket trades --market 0x7ad403c... --outcome Yes --limit 20
```

### "Script over multiple markets"

```bash
# Pipe slugs
for slug in $(polymarket trending --limit 10 --json | jq -r '.[].markets[0].slug'); do
    echo "=== $slug ==="
    polymarket quick "$slug" --depth 1
done
```

## Output conventions

- Prices are probabilities. `0.652` → "65.2%".
- `Buy` price = current best ask (cost to buy Yes token).
- `Sell` price = current best bid (proceeds from selling Yes token).
- `Mid` = CLOB's reported midpoint (may differ from naive (bid+ask)/2 — see note below).
- `Last` = most recent trade price.
- Volumes are in USDC.

### When mid looks weird

If you see:
```
Best bid 0.1% | Best ask 99.9%
Mid: 20.8%
```

The book is being pushed to extremes by large resting orders but the actual traded price is somewhere else. `quick` automatically prints a NOTE when book mid differs from CLOB mid by >5 percentage points. In that case, trust `Last` and `trades`, not the book.

## Rate limits

Generous, unlikely to hit:
- Gamma: 4,000 req / 10s
- CLOB: 9,000 req / 10s
- Data: 1,000 req / 10s

## Roadmap

- [ ] CLOB trading (L2 auth, EIP-712 signing) — needs wallet
- [ ] Relayer API (gasless txs)
- [ ] WebSocket market channel (real-time book updates)
- [ ] WebSocket user channel (fills, order updates) — needs auth
- [ ] Data API v2 — positions / PnL / activity (per wallet)
- [ ] async version (httpx + websockets) for high-frequency monitoring

## Files

- `polymarket.py` — the CLI (single file, stdlib only)
- `README.md` — this file
- `test_smoke.sh` — hits each API once to confirm connectivity
- `aliases.sh` — shell shortcuts (pmsearch, pmquick, pmtop, etc.)
