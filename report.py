#!/usr/bin/env python3
"""Generate a Polymarket snapshot digest HTML.

Pulls from CLOB + Data API (Gamma is filtered on some networks).
Output: ./report.html

For full documentation, see the polymarket-digest skill in this repo's
SKILL ecosystem (news-digest/polymarket-digest).
"""
import json
import ssl
import sys
import urllib.request
from datetime import datetime, timezone

CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"FAIL {url}: {e}", file=sys.stderr)
        return None


def fmt_pct(p):
    if p is None:
        return "?"
    return f"{float(p) * 100:.1f}%"


def fmt_spread(s):
    if s is None:
        return "—"
    return f"{float(s) * 100:.1f} pp"


# --- Pull data ---
markets = _get(f"{CLOB}/markets?limit=500")
if not markets or "data" not in markets:
    print("Could not fetch CLOB markets", file=sys.stderr)
    sys.exit(1)

data = markets["data"]


def rank(m):
    if m.get("accepting_orders"):
        return 0
    if m.get("active") and not m.get("closed"):
        return 1
    if not m.get("closed"):
        return 2
    return 3


data.sort(key=rank)

rows = []
for m in data:
    if not m.get("tokens") or len(m["tokens"]) < 2:
        continue
    yes_t = next((t for t in m["tokens"] if t.get("outcome") == "Yes"), m["tokens"][0])
    no_t = next((t for t in m["tokens"] if t.get("outcome") == "No"), m["tokens"][1])
    yp, np = yes_t.get("price"), no_t.get("price")
    spread = (np - yp) if (yp is not None and np is not None) else None
    rows.append({
        "question": m.get("question", "?"),
        "yes_price": yp, "no_price": np, "spread": spread,
        "trading": bool(m.get("accepting_orders")),
        "closed": bool(m.get("closed")),
    })
    if len(rows) >= 30:
        break

trades = _get(f"{DATA}/trades?limit=30") or []

# Sort: trading first, then by |spread| desc
rows.sort(key=lambda r: (not r["trading"], -abs(r["spread"]) if r["spread"] is not None else 0))

now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# --- Render HTML ---
market_rows_html = ""
for r in rows:
    spread_class = ""
    if r["spread"] is not None:
        if abs(r["spread"]) > 0.1:
            spread_class = "spread-huge"
        elif abs(r["spread"]) > 0.02:
            spread_class = "spread-wide"
        elif abs(r["spread"]) < 0.001:
            spread_class = "spread-locked"
    badge = "\U0001F7E2" if r["trading"] else ("\u26AA" if r["closed"] else "\U0001F7E1")
    cls = "trading" if r["trading"] else ""
    market_rows_html += (
        "\n    <tr class=\"" + spread_class + " " + cls + "\">"
        "<td class=\"q\">" + badge + " " + r["question"] + "</td>"
        "<td class=\"num yes\">" + fmt_pct(r["yes_price"]) + "</td>"
        "<td class=\"num no\">" + fmt_pct(r["no_price"]) + "</td>"
        "<td class=\"num spread\">" + fmt_spread(r["spread"]) + "</td>"
        "</tr>"
    )

trades_html = ""
for t in trades[:20]:
    side = t.get("side", "?")
    cls = "buy" if side == "BUY" else "sell"
    try:
        ts = datetime.fromtimestamp(int(t.get("timestamp", 0)), tz=timezone.utc).strftime("%H:%M:%S")
    except Exception:
        ts = "?"
    price = fmt_pct(t.get("price"))
    try:
        size_str = f"{float(t.get('size', 0)):>8.2f}"
    except (ValueError, TypeError):
        size_str = "?"
    out = t.get("outcome", "?")
    title = (t.get("title", "?") or "?")[:60]
    trades_html += (
        "\n    <tr class=\"" + cls + "\">"
        "<td class=\"time\">" + ts + "</td>"
        "<td class=\"side\">" + side + "</td>"
        "<td class=\"num\">" + price + "</td>"
        "<td class=\"num\">x" + size_str + "</td>"
        "<td class=\"out\">[" + out + "]</td>"
        "<td class=\"title\">" + title + "</td>"
        "</tr>"
    )

html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymarket Snapshot &mdash; """ + now_utc + """</title>
<style>
  :root {
    --bg: #0e1117; --panel: #161b22; --panel-alt: #1a1f2b;
    --fg: #c9d1d9; --fg-dim: #8b949e; --border: #30363d;
    --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Consolas, monospace;
    margin: 0; padding: 24px; line-height: 1.5;
  }
  h1 { color: var(--accent); margin: 0 0 4px 0; font-size: 22px; }
  .sub { color: var(--fg-dim); margin-bottom: 24px; font-size: 13px; }
  h2 {
    color: var(--fg-dim); font-size: 12px; text-transform: uppercase;
    letter-spacing: 1px; margin: 32px 0 12px 0;
    padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }
  table { width: 100%; border-collapse: collapse; background: var(--panel); font-size: 13px; }
  th {
    text-align: left; color: var(--fg-dim); font-weight: normal;
    padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--panel-alt);
  }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
  tr:hover td { background: var(--panel-alt); }
  td.q { max-width: 800px; }
  td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  td.yes { color: var(--green); font-weight: 600; }
  td.no  { color: var(--red);   font-weight: 600; }
  td.spread { color: var(--fg-dim); }
  tr.spread-huge td.spread { color: var(--yellow); font-weight: 600; }
  tr.spread-wide td.spread  { color: var(--yellow); }
  tr.spread-locked td.spread { color: var(--green); }
  tr.trading td.q { font-weight: 600; }
  tr.buy td.side  { color: var(--green); font-weight: 600; }
  tr.sell td.side { color: var(--red);   font-weight: 600; }
  td.time { color: var(--fg-dim); font-variant-numeric: tabular-nums; }
  td.out  { color: var(--accent); }
  td.title { color: var(--fg-dim); }
  .meta {
    display: flex; gap: 24px; margin: 16px 0 32px 0; padding: 12px 16px;
    background: var(--panel); border-left: 3px solid var(--accent); font-size: 13px;
  }
  .meta b { color: var(--fg-dim); font-weight: normal; margin-right: 6px; }
  .legend { color: var(--fg-dim); font-size: 12px; margin-top: 8px; }
</style>
</head>
<body>
<h1>Polymarket Snapshot</h1>
<div class="sub">Generated """ + now_utc + """</div>

<div class="meta">
  <div><b>Markets shown:</b>""" + str(len(rows)) + """</div>
  <div><b>Of which trading now:</b>""" + str(sum(1 for r in rows if r['trading'])) + """</div>
  <div><b>Trades shown:</b>""" + str(min(20, len(trades))) + """</div>
  <div><b>Data sources:</b>CLOB API, Data API</div>
</div>

<h2>Markets ranked by trading status, then by |Yes &minus; No| spread</h2>
<table>
  <thead>
    <tr><th>Question</th><th>Yes</th><th>No</th><th>Yes&minus;No</th></tr>
  </thead>
  <tbody>""" + market_rows_html + """
  </tbody>
</table>
<div class="legend">
  &#x1F7E2; = currently accepting orders &middot; &#x1F7E1; = active not yet closed but not taking orders &middot; &#x26AA; = historical/closed
  Yellow spread = wide mispricing (potential arb or thin book).
  Green spread &asymp; 0 = Yes + No prices sum to ~100%, no arb.
</div>

<h2>Recent trades (latest first)</h2>
<table>
  <thead>
    <tr><th>Time</th><th>Side</th><th>Price</th><th>Size</th><th>Outcome</th><th>Market</th></tr>
  </thead>
  <tbody>""" + trades_html + """
  </tbody>
</table>
</body>
</html>
"""

with open("report.html", "w") as f:
    f.write(html)

print(f"Report: report.html ({len(html)} bytes, {len(rows)} markets, {len(trades)} trades)")
