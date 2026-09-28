#!/usr/bin/env python3
"""Polymarket CLI — query prediction market data (read-only).

Covers Gamma (search/events/markets), CLOB (price/book/history), Data (trades).
No authentication required. Use --json on any command for machine-readable output.

Usage:
    python3 polymarket.py search "bitcoin"
    python3 polymarket.py trending [--limit 10]
    python3 polymarket.py market <slug> [--json]
    python3 polymarket.py event <slug>
    python3 polymarket.py price <token_id> [--side buy|sell]
    python3 polymarket.py book <token_id> [--depth 10]
    python3 polymarket.py history <condition_id> [--interval all] [--fidelity 50]
    python3 polymarket.py trades [--limit 10] [--market CONDITION_ID] [--outcome Yes|No]
    python3 polymarket.py token <token_id>      # price + book snapshot
    python3 polymarket.py quick <market_slug>   # market + both token prices + book
"""
import argparse
import json
import os
import ssl
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Union, Optional

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"

# Browser-like User-Agent. Polymarket's Cloudflare returns 403/1010
# (browser integrity check) for the default urllib User-Agent, so we
# pretend to be Chrome. Override with POLYMARKET_USER_AGENT env var.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class PolymarketError(Exception):
    """Raised by cmd_* functions when an API call fails.

    CLI mode catches this in main() and exits with the message.
    GUI mode catches this on the worker thread and shows it in the UI.
    """
    pass


# ---------- Client ----------

class PolymarketClient:
    """HTTP client wrapping urllib with proper error handling.

    Replaces module-level globals so multiple instances can have
    different settings (e.g., one insecure, one not).
    """

    def __init__(self, *, insecure: bool = False, user_agent: Optional[str] = None,
                 timeout: float = 20.0):
        self.user_agent = user_agent or os.environ.get("POLYMARKET_USER_AGENT", _DEFAULT_UA)
        self.insecure = insecure or os.environ.get("POLYMARKET_INSECURE") == "1"
        self.timeout = timeout

    def get(self, url: str) -> Union[dict, list]:
        """GET request, return parsed JSON. Raises PolymarketError on failure."""
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        ctx = ssl._create_unverified_context() if self.insecure else None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            host = urllib.parse.urlparse(url).netloc
            if "1010" in body or "browser integrity" in body.lower():
                raise PolymarketError(
                    f"Cloudflare blocked {host} (browser integrity check 1010). "
                    f"Try setting POLYMARKET_USER_AGENT to a normal browser string."
                )
            if e.code in (403, 404) and ("<html" in body.lower() or "blocked" in body.lower() or "封鎖" in body):
                raise PolymarketError(
                    f"Network blocked {host} (HTTP {e.code}). "
                    f"Try a different network (mobile hotspot / VPN)."
                )
            raise PolymarketError(f"HTTP {e.code} {e.reason} — {body}")
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason or "certificate verify failed" in reason.lower():
                raise PolymarketError(
                    "SSL certificate verification failed. "
                    "Your network is MITM-ing HTTPS — retry with --insecure."
                )
            raise PolymarketError(f"Connection error: {e.reason}")


# Default client used by the cmd_xxx functions below. Tests / callers
# can override by passing a Client into specific functions (not yet
# threaded through — out of scope for refactor A).
_CLIENT = PolymarketClient()


def _get(url: str) -> Union[dict, list]:
    """Module-level convenience wrapper around the default client."""
    return _CLIENT.get(url)


# ---------- Formatters ----------

def _parse_json_field(val):
    """Parse double-encoded JSON fields (outcomePrices, outcomes, clobTokenIds)."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def _fmt_pct(price) -> str:
    try:
        return f"{float(price) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(price)


def _fmt_volume(vol) -> str:
    try:
        v = float(vol)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.0f}"
    except (ValueError, TypeError):
        return str(vol)


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return str(ts)


def emit(data, as_json: bool):
    """Print as JSON or pretty-print."""
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2, ensure_ascii=False))


# ---------- Printers ----------

def _print_market(m: dict, indent: str = "", as_json: bool = False):
    if as_json:
        return emit(m, True)
    question = m.get("question", "?")
    prices = _parse_json_field(m.get("outcomePrices", "[]"))
    outcomes = _parse_json_field(m.get("outcomes", "[]"))
    vol = _fmt_volume(m.get("volume", 0))
    closed = m.get("closed", False)
    status = " [CLOSED]" if closed else ""

    if isinstance(prices, list) and len(prices) >= 2:
        outcome_labels = outcomes if isinstance(outcomes, list) else ["Yes", "No"]
        price_str = " / ".join(
            f"{outcome_labels[i]}: {_fmt_pct(prices[i])}"
            for i in range(min(len(prices), len(outcome_labels)))
        )
        print(f"{indent}{question}{status}")
        print(f"{indent}  {price_str}  |  Volume: {vol}")
    else:
        print(f"{indent}{question}{status}  |  Volume: {vol}")

    slug = m.get("slug", "")
    if slug:
        print(f"{indent}  slug: {slug}")


# ---------- Commands ----------

def cmd_search(query: str, limit: int, as_json: bool):
    q = urllib.parse.quote(query)
    data = _get(f"{GAMMA}/public-search?q={q}")
    if as_json:
        return emit(data, True)
    events = data.get("events", [])
    total = data.get("pagination", {}).get("totalResults", len(events))
    print(f"Found {total} results for \"{query}\" (showing first {min(limit, len(events))}):\n")
    for evt in events[:limit]:
        print(f"=== {evt['title']} ===")
        print(f"  Volume: {_fmt_volume(evt.get('volume', 0))}  |  slug: {evt.get('slug', '')}")
        markets = evt.get("markets", [])
        for m in markets[:5]:
            _print_market(m, indent="  ")
        if len(markets) > 5:
            print(f"  ... and {len(markets) - 5} more markets")
        print()


def cmd_trending(limit: int, as_json: bool):
    events = _get(f"{GAMMA}/events?limit={limit}&active=true&closed=false&order=volume&ascending=false")
    if as_json:
        return emit(events, True)
    print(f"Top {len(events)} trending events:\n")
    for i, evt in enumerate(events, 1):
        print(f"{i}. {evt['title']}")
        print(f"   Volume: {_fmt_volume(evt.get('volume', 0))}  |  Markets: {len(evt.get('markets', []))}")
        print(f"   slug: {evt.get('slug', '')}")
        markets = evt.get("markets", [])
        for m in markets[:3]:
            _print_market(m, indent="   ")
        if len(markets) > 3:
            print(f"   ... and {len(markets) - 3} more markets")
        print()


def cmd_market(slug: str, as_json: bool):
    markets = _get(f"{GAMMA}/markets?slug={urllib.parse.quote(slug)}")
    if not markets:
        raise PolymarketError(f"No market found with slug: {slug}")
    m = markets[0]
    if as_json:
        return emit(m, True)
    print(f"Market: {m.get('question', '?')}")
    print(f"Status: {'CLOSED' if m.get('closed') else 'ACTIVE'}")
    _print_market(m)
    print(f"\n  conditionId: {m.get('conditionId', 'N/A')}")
    tokens = _parse_json_field(m.get("clobTokenIds", "[]"))
    if isinstance(tokens, list):
        outcomes = _parse_json_field(m.get("outcomes", "[]"))
        for i, t in enumerate(tokens):
            label = outcomes[i] if isinstance(outcomes, list) and i < len(outcomes) else f"Outcome {i}"
            print(f"  token ({label}): {t}")
    desc = m.get("description", "")
    if desc:
        print(f"\n  Description: {desc[:500]}")


def cmd_event(slug: str, as_json: bool):
    events = _get(f"{GAMMA}/events?slug={urllib.parse.quote(slug)}")
    if not events:
        raise PolymarketError(f"No event found with slug: {slug}")
    evt = events[0]
    if as_json:
        return emit(evt, True)
    print(f"Event: {evt['title']}")
    print(f"Volume: {_fmt_volume(evt.get('volume', 0))}")
    print(f"Status: {'CLOSED' if evt.get('closed') else 'ACTIVE'}")
    print(f"Markets: {len(evt.get('markets', []))}\n")
    for m in evt.get("markets", []):
        _print_market(m, indent="  ")
        print()


def cmd_price(token_id: str, side: str, as_json: bool):
    quote = _get(f"{CLOB}/price?token_id={token_id}&side={side}")
    mid = _get(f"{CLOB}/midpoint?token_id={token_id}")
    spread = _get(f"{CLOB}/spread?token_id={token_id}")
    if as_json:
        return emit({"token_id": token_id, "side": side, **quote, "midpoint": mid.get("mid"), "spread": spread.get("spread")}, True)
    print(f"Token: {token_id[:30]}...")
    print(f"  {side.upper()} price: {_fmt_pct(quote.get('price', '?'))}")
    print(f"  Midpoint:  {_fmt_pct(mid.get('mid', '?'))}")
    print(f"  Spread:    {spread.get('spread', '?')}")


def cmd_book(token_id: str, depth: int, as_json: bool):
    book = _get(f"{CLOB}/book?token_id={token_id}")
    if as_json:
        return emit(book, True)
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    last = book.get("last_trade_price", "?")
    print(f"Orderbook for {token_id[:30]}...")
    print(f"Last trade: {_fmt_pct(last)}  |  Tick size: {book.get('tick_size', '?')}  |  Min size: {book.get('min_order_size', '?')}")
    print(f"\n  Top bids ({len(bids)} total):")
    for b in bids[:depth]:
        print(f"    {_fmt_pct(b['price']):>7}  |  Size: {float(b['size']):>10.2f}")
    print(f"\n  Top asks ({len(asks)} total):")
    for a in asks[:depth]:
        print(f"    {_fmt_pct(a['price']):>7}  |  Size: {float(a['size']):>10.2f}")


def cmd_history(condition_id: str, interval: str, fidelity: int, as_json: bool):
    data = _get(f"{CLOB}/prices-history?market={condition_id}&interval={interval}&fidelity={fidelity}")
    history = data.get("history", [])
    if as_json:
        return emit(data, True)
    if not history:
        print("No price history available for this market.")
        return
    print(f"Price history ({len(history)} points, interval={interval}):\n")
    for pt in history:
        ts = _fmt_ts(pt["t"])
        price = _fmt_pct(pt["p"])
        bar = "█" * int(float(pt["p"]) * 40)
        print(f"  {ts}  {price:>7}  {bar}")


def cmd_trades(limit: int, market: Optional[str], outcome: Optional[str], as_json: bool):
    url = f"{DATA}/trades?limit={limit}"
    if market:
        url += f"&market={market}"
    trades = _get(url)
    if not isinstance(trades, list):
        raise PolymarketError(f"Unexpected response: {trades}")
    if outcome:
        outcome_lower = outcome.lower()
        trades = [t for t in trades if str(t.get("outcome", "")).lower() == outcome_lower]
    if as_json:
        return emit(trades, True)
    print(f"Recent trades ({len(trades)}):\n")
    for t in trades:
        side = t.get("side", "?")
        price = _fmt_pct(t.get("price", "?"))
        try:
            size = f"{float(t.get('size', 0)):>8.2f}"
        except (ValueError, TypeError):
            size = str(t.get("size", "?"))
        out = t.get("outcome", "?")
        title = (t.get("title", "?") or "?")[:55]
        ts = _fmt_ts(t.get("timestamp", ""))
        print(f"  {side:4}  {price:>7}  x{size}  [{out}]  {title}  @ {ts}")


def _fetch_token_snapshot(token_id: str) -> dict:
    """Fetch buy/sell/mid/spread/book for one token. Used by cmd_token and cmd_quick."""
    buy = _get(f"{CLOB}/price?token_id={token_id}&side=buy")
    sell = _get(f"{CLOB}/price?token_id={token_id}&side=sell")
    mid = _get(f"{CLOB}/midpoint?token_id={token_id}")
    spread = _get(f"{CLOB}/spread?token_id={token_id}")
    book = _get(f"{CLOB}/book?token_id={token_id}")
    return {
        "buy": buy.get("price"),
        "sell": sell.get("price"),
        "mid": mid.get("mid"),
        "spread": spread.get("spread"),
        "last_trade": book.get("last_trade_price"),
        "tick_size": book.get("tick_size"),
        "min_order_size": book.get("min_order_size"),
        "best_bid": book.get("bids", [{}])[0].get("price") if book.get("bids") else None,
        "best_ask": book.get("asks", [{}])[0].get("price") if book.get("asks") else None,
        "bid_depth": len(book.get("bids", [])),
        "ask_depth": len(book.get("asks", [])),
        "bids": book.get("bids", []),
        "asks": book.get("asks", []),
    }


def cmd_token(token_id: str, depth: int, as_json: bool):
    """One-shot snapshot: price (buy/sell), midpoint, spread, book."""
    s = _fetch_token_snapshot(token_id)
    snapshot = {k: v for k, v in s.items() if k not in ("bids", "asks")}
    snapshot["token_id"] = token_id
    if as_json:
        return emit(snapshot, True)
    print(f"Token: {token_id}")
    print(f"  Buy:       {_fmt_pct(snapshot['buy'])}")
    print(f"  Sell:      {_fmt_pct(snapshot['sell'])}")
    print(f"  Mid:       {_fmt_pct(snapshot['mid'])}")
    print(f"  Spread:    {snapshot['spread']}")
    print(f"  Last:      {_fmt_pct(snapshot['last_trade'])}")
    print(f"  Tick:      {snapshot['tick_size']}  |  Min size: {snapshot['min_order_size']}")
    print(f"  Best bid:  {_fmt_pct(snapshot['best_bid'])}  ({snapshot['bid_depth']} levels)")
    print(f"  Best ask:  {_fmt_pct(snapshot['best_ask'])}  ({snapshot['ask_depth']} levels)")


def cmd_quick(slug: str, depth: int, as_json: bool):
    """Market + both token prices + both order books in one shot."""
    markets = _get(f"{GAMMA}/markets?slug={urllib.parse.quote(slug)}")
    if not markets:
        raise PolymarketError(f"No market found with slug: {slug}")
    m = markets[0]
    tokens = _parse_json_field(m.get("clobTokenIds", "[]"))
    outcomes = _parse_json_field(m.get("outcomes", []))

    if not isinstance(tokens, list) or len(tokens) < 2:
        raise PolymarketError("Market has no tradable CLOB tokens.")

    snapshots = []
    for i, t in enumerate(tokens):
        s = _fetch_token_snapshot(t)
        label = outcomes[i] if isinstance(outcomes, list) and i < len(outcomes) else f"Outcome {i}"
        snapshots.append({
            "outcome": label,
            "token_id": t,
            "buy": s["buy"], "sell": s["sell"], "mid": s["mid"],
            "last_trade": s["last_trade"],
            "best_bid": s["best_bid"], "best_ask": s["best_ask"],
            "bids": s["bids"][:depth],
            "asks": s["asks"][:depth],
        })

    if as_json:
        return emit({
            "market": {
                "question": m.get("question"),
                "slug": m.get("slug"),
                "conditionId": m.get("conditionId"),
                "closed": m.get("closed"),
                "volume": m.get("volume"),
            },
            "outcomes": snapshots,
        }, True)

    print(f"=== {m.get('question')} ===")
    print(f"Status: {'CLOSED' if m.get('closed') else 'ACTIVE'}  |  Volume: {_fmt_volume(m.get('volume', 0))}")
    print(f"conditionId: {m.get('conditionId')}\n")
    for s in snapshots:
        print(f"  [{s['outcome']}]  Buy: {_fmt_pct(s['buy'])}  Sell: {_fmt_pct(s['sell'])}  Mid: {_fmt_pct(s['mid'])}  Last: {_fmt_pct(s['last_trade'])}")
        bids = s["bids"]
        asks = s["asks"]
        if s['best_bid'] and s['best_ask']:
            try:
                implied = (float(s['best_bid']) + float(s['best_ask'])) / 2
                if abs(implied - float(s['mid'])) > 0.05:
                    print(f"    NOTE: book mid {_fmt_pct(implied)} differs from CLOB mid {_fmt_pct(s['mid'])} (>5pp) — check history/trades for true price.")
            except (ValueError, TypeError):
                pass
        print(f"    Best bid {_fmt_pct(s['best_bid'])} | Best ask {_fmt_pct(s['best_ask'])}  ({len(bids)}/{len(asks)} levels)")
        for b in bids[:depth]:
            print(f"      bid {_fmt_pct(b['price']):>7}  x{float(b['size']):>8.2f}")
        for a in asks[:depth]:
            print(f"      ask {_fmt_pct(a['price']):>7}  x{float(a['size']):>8.2f}")
        print()


# ---------- CLI ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polymarket",
        description="Polymarket read-only CLI (Gamma + CLOB + Data API).",
    )
    p.add_argument("--json", action="store_true", help="Output JSON instead of formatted text.")
    p.add_argument("--insecure", action="store_true",
                   help="Skip SSL certificate verification (for corporate MITM networks). "
                        "Equivalent to POLYMARKET_INSECURE=1.")

    sub = p.add_subparsers(dest="cmd", required=True)
    parent_json = argparse.ArgumentParser(add_help=False)
    parent_json.add_argument("--json", action="store_true", help="Output JSON instead of formatted text.")
    # NOTE: --insecure is NOT in parent_json — argparse gets confused when
    # the same flag is on both the main parser and every subparser (via
    # parents=). Keeping it only on the main parser so `args.insecure`
    # reliably reflects the user's flag.

    def _bind(func, arg_names):
        """Bind a cmd_xxx(query, limit, json) to argparse args namespace.

        arg_names lists the parameter names in order. The argparse
        attribute is `json` (from --json) but cmd_xxx params may use
        any name — this mapping decouples the two.
        """
        return lambda args: func(*[getattr(args, name) for name in arg_names])

    s = sub.add_parser("search", help="Search events/markets by query.", parents=[parent_json])
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=_bind(cmd_search, ["query", "limit", "json"]))

    s = sub.add_parser("trending", help="Top events by volume.", parents=[parent_json])
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=_bind(cmd_trending, ["limit", "json"]))

    s = sub.add_parser("market", help="Get a single market by slug.", parents=[parent_json])
    s.add_argument("slug")
    s.set_defaults(func=_bind(cmd_market, ["slug", "json"]))

    s = sub.add_parser("event", help="Get a single event by slug.", parents=[parent_json])
    s.add_argument("slug")
    s.set_defaults(func=_bind(cmd_event, ["slug", "json"]))

    s = sub.add_parser("price", help="Current price for a token.", parents=[parent_json])
    s.add_argument("token_id")
    s.add_argument("--side", choices=["buy", "sell"], default="buy")
    s.set_defaults(func=_bind(cmd_price, ["token_id", "side", "json"]))

    s = sub.add_parser("book", help="Orderbook for a token.", parents=[parent_json])
    s.add_argument("token_id")
    s.add_argument("--depth", type=int, default=10)
    s.set_defaults(func=_bind(cmd_book, ["token_id", "depth", "json"]))

    s = sub.add_parser("history", help="Price history for a market (by conditionId).", parents=[parent_json])
    s.add_argument("condition_id")
    s.add_argument("--interval", default="all", choices=["all", "1d", "1w", "1m", "3m", "6m", "1y"])
    s.add_argument("--fidelity", type=int, default=50)
    s.set_defaults(func=_bind(cmd_history, ["condition_id", "interval", "fidelity", "json"]))

    s = sub.add_parser("trades", help="Recent trades.", parents=[parent_json])
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--market", help="Filter by conditionId")
    s.add_argument("--outcome", choices=["Yes", "No"], help="Filter by outcome")
    s.set_defaults(func=_bind(cmd_trades, ["limit", "market", "outcome", "json"]))

    s = sub.add_parser("token", help="One-shot snapshot: price + book for a token.", parents=[parent_json])
    s.add_argument("token_id")
    s.add_argument("--depth", type=int, default=5)
    s.set_defaults(func=_bind(cmd_token, ["token_id", "depth", "json"]))

    s = sub.add_parser("quick", help="Market + both token prices + books in one shot.", parents=[parent_json])
    s.add_argument("market_slug")
    s.add_argument("--depth", type=int, default=5)
    s.set_defaults(func=_bind(cmd_quick, ["market_slug", "depth", "json"]))

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Replace the default client with one matching CLI flags.
    # Subsequent _get() calls (via the module-level _CLIENT) will
    # pick up these settings.
    global _CLIENT
    _CLIENT = PolymarketClient(insecure=getattr(args, "insecure", False))

    try:
        args.func(args)
    except PolymarketError as e:
        # CLI mode: print the friendly message and exit non-zero.
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
