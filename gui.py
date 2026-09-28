#!/usr/bin/env python3
"""Polymarket Tkinter Dashboard.

Dark-themed local desktop GUI that wraps the existing polymarket CLI
to display:
  - Trending markets (left panel, auto-refresh 30s)
  - Selected market detail + order book + price history sparkline (center)
  - Recent trades ticker (bottom strip, auto-scroll every 10s)

Reuses PolymarketClient + cmd_* from polymarket.py. No third-party deps.

Usage:
    python3 gui.py                # normal
    python3 gui.py --insecure     # skip SSL cert verification
    POLYMARKET_INSECURE=1 python3 gui.py
"""
import argparse
import json
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional

# Reuse everything from the CLI module.
from polymarket import (
    PolymarketClient,
    PolymarketError,
    GAMMA,
    CLOB,
    DATA,
    _DEFAULT_UA,
)


# ---------- Dark theme palette ----------

BG          = "#0e1117"   # window bg
PANEL       = "#161b22"   # panel bg
PANEL_ALT   = "#1a1f2b"   # alt panel (slightly lighter)
FG          = "#c9d1d9"   # primary text
FG_DIM      = "#8b949e"   # secondary text
BORDER      = "#30363d"
ACCENT      = "#58a6ff"   # blue
GREEN       = "#3fb950"   # bid / buy
RED         = "#f85149"   # ask / sell
YELLOW      = "#d29922"   # warning
FONT        = ("Consolas", 10)
FONT_BOLD   = ("Consolas", 10, "bold")
FONT_TITLE  = ("Consolas", 12, "bold")
FONT_SMALL  = ("Consolas", 9)


# ---------- Worker thread ----------

class Worker(threading.Thread):
    """Runs cmd_* functions off the UI thread, posts results to a queue.

    Each submitted job is `(callable, kwargs, result_tag, callback)`.
    The worker calls `callable(**kwargs)`; if it raises PolymarketError,
    the exception message becomes the result. The callback (called from
    the UI thread via the queue drain) receives `(result_tag, value_or_err)`.
    """

    def __init__(self, results: queue.Queue):
        super().__init__(daemon=True)
        self._jobs: queue.Queue = queue.Queue()
        self._results = results

    def submit(self, callable_, kwargs: dict, tag: str):
        self._jobs.put((callable_, kwargs, tag))

    def run(self):
        while True:
            callable_, kwargs, tag = self._jobs.get()
            try:
                value = callable_(**kwargs)
                self._results.put((tag, value, None))
            except PolymarketError as e:
                self._results.put((tag, None, str(e)))
            except Exception as e:
                self._results.put((tag, None, f"{type(e).__name__}: {e}"))


# ---------- Formatters (Tkinter versions) ----------

def fmt_pct(p) -> str:
    try:
        return f"{float(p) * 100:.1f}%"
    except (ValueError, TypeError):
        return "?"

def fmt_vol(v) -> str:
    try:
        v = float(v)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.0f}"
    except (ValueError, TypeError):
        return "?"


# ---------- Widget helpers ----------

def make_label(parent, text, fg=FG, bg=PANEL, font=FONT, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, anchor="w", **kw)


def make_panel(parent, title: Optional[str] = None):
    """Return (frame, content_frame). A titled bordered panel."""
    outer = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=1, highlightbackground=BORDER)
    if title:
        title_bar = tk.Frame(outer, bg=PANEL_ALT, height=22)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text=f"  {title}", fg=FG_DIM, bg=PANEL_ALT,
                 font=FONT_BOLD, anchor="w").pack(side="left", fill="x", expand=True)
    content = tk.Frame(outer, bg=PANEL, bd=0)
    content.pack(fill="both", expand=True)
    return outer, content


# ---------- Sparkline (pure Canvas) ----------

class Sparkline(tk.Canvas):
    """Tiny line chart drawn on a Canvas widget. No matplotlib."""

    def __init__(self, parent, height=80, **kw):
        super().__init__(parent, height=height, bg=PANEL, highlightthickness=0, **kw)

    def plot(self, points):
        """points: list of (timestamp, price) where price in 0..1."""
        self.delete("all")
        if not points or len(points) < 2:
            self.create_text(4, 4, anchor="nw", text="(no history)", fill=FG_DIM, font=FONT_SMALL)
            return
        w = self.winfo_width() or self.winfo_reqwidth()
        h = self.winfo_height() or self.winfo_reqheight()
        prices = [p for _, p in points]
        lo, hi = min(prices), max(prices)
        if hi - lo < 0.001:
            hi = lo + 0.001
        n = len(points)
        # Map point i to (x, y)
        coords = []
        for i, (_, p) in enumerate(points):
            x = 4 + (w - 8) * i / (n - 1)
            y = h - 4 - (h - 8) * (p - lo) / (hi - lo)
            coords.append((x, y))
        # Filled area under line
        area = coords + [(w - 4, h), (4, h)]
        self.create_polygon(area, fill="#1f3a5f", outline="")
        # Line
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            self.create_line(x1, y1, x2, y2, fill=ACCENT, width=1)
        # Last point dot
        lx, ly = coords[-1]
        self.create_oval(lx - 2, ly - 2, lx + 2, ly + 2, fill=ACCENT, outline="")


# ---------- Main app ----------

class Dashboard(tk.Tk):
    REFRESH_TRENDING_MS = 30_000
    REFRESH_TRADES_MS = 10_000

    def __init__(self, *, insecure: bool = False):
        super().__init__()
        self.title("Polymarket Dashboard")
        self.geometry("1280x800")
        self.configure(bg=BG)

        self.client = PolymarketClient(insecure=insecure)
        self.results: queue.Queue = queue.Queue()
        self.worker = Worker(self.results)
        self.worker.start()
        self.after(100, self._drain_results)

        # State
        self.trending_markets: list = []   # list of (slug, question, volume)
        self.selected_slug: Optional[str] = None
        self.trades_enabled = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="● idle")
        self.search_var = tk.StringVar()

        self._build_ui()
        self.after(500, self.refresh_trending)
        if self.trades_enabled.get():
            self.after(800, self.refresh_trades)

    # ---- UI construction ----

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=PANEL_ALT, height=44)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)
        tk.Label(top, text="  Polymarket", fg=ACCENT, bg=PANEL_ALT,
                 font=("Consolas", 13, "bold")).pack(side="left")
        # Search
        search_frame = tk.Frame(top, bg=PANEL_ALT)
        search_frame.pack(side="left", padx=20)
        tk.Label(search_frame, text="search:", fg=FG_DIM, bg=PANEL_ALT, font=FONT_SMALL).pack(side="left")
        entry = tk.Entry(search_frame, textvariable=self.search_var, width=30,
                         bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                         font=FONT, highlightthickness=1, highlightbackground=BORDER)
        entry.pack(side="left", padx=6, ipady=3)
        entry.bind("<Return>", lambda _e: self.do_search())
        tk.Button(search_frame, text="go", command=self.do_search,
                  bg=PANEL, fg=FG, activebackground=ACCENT, activeforeground=BG,
                  relief="flat", font=FONT, padx=10).pack(side="left")
        # Trades toggle
        tk.Checkbutton(top, text="trades ticker", variable=self.trades_enabled,
                       fg=FG_DIM, bg=PANEL_ALT, selectcolor=PANEL,
                       activebackground=PANEL_ALT, font=FONT_SMALL,
                       command=self._toggle_trades).pack(side="right", padx=12)
        # Refresh button
        tk.Button(top, text="⟳ refresh", command=self.refresh_trending,
                  bg=PANEL, fg=FG, activebackground=ACCENT, activeforeground=BG,
                  relief="flat", font=FONT, padx=10).pack(side="right", padx=4)
        # Status
        tk.Label(top, textvariable=self.status_var, fg=YELLOW, bg=PANEL_ALT,
                 font=FONT_SMALL).pack(side="right", padx=12)

        # Main split: left list / right detail
        main = tk.PanedWindow(self, orient="horizontal", bg=BG, sashwidth=4,
                              bd=0, relief="flat")
        main.pack(fill="both", expand=True, padx=6, pady=6)

        # Left panel
        left_outer, left = make_panel(main, title="MARKETS")
        main.add(left_outer, minsize=280, width=320)
        # Listbox + scrollbar
        list_frame = tk.Frame(left, bg=PANEL)
        list_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self.listbox = tk.Listbox(list_frame, bg=PANEL, fg=FG, selectbackground=ACCENT,
                                  selectforeground=BG, font=FONT, relief="flat",
                                  highlightthickness=0, activestyle="none",
                                  borderwidth=0)
        sb = tk.Scrollbar(list_frame, command=self.listbox.yview, bg=PANEL,
                          troughcolor=PANEL, activebackground=BORDER)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_market_select)

        # Right panel: market detail
        right_outer, right = make_panel(main, title="MARKET DETAIL")
        main.add(right_outer, minsize=600)
        # Header strip
        self.header_var = tk.StringVar(value="(no market selected)")
        tk.Label(right, textvariable=self.header_var, fg=FG, bg=PANEL,
                 font=FONT_TITLE, anchor="w", justify="left",
                 wraplength=900).pack(fill="x", padx=10, pady=(8, 4))
        # Outcomes + book
        body = tk.Frame(right, bg=PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        # Left side of body: outcomes
        outcomes_frame = tk.Frame(body, bg=PANEL)
        outcomes_frame.pack(side="left", fill="both", expand=True)
        tk.Label(outcomes_frame, text="OUTCOMES", fg=FG_DIM, bg=PANEL,
                 font=FONT_BOLD, anchor="w").pack(fill="x")
        self.outcomes_text = tk.Text(outcomes_frame, height=10, bg=PANEL, fg=FG,
                                     font=FONT, relief="flat", highlightthickness=0,
                                     wrap="none", borderwidth=0)
        self.outcomes_text.pack(fill="both", expand=True, pady=(2, 0))
        self.outcomes_text.configure(state="disabled")
        # Right side of body: order book
        book_frame = tk.Frame(body, bg=PANEL, width=360)
        book_frame.pack(side="right", fill="y", padx=(10, 0))
        book_frame.pack_propagate(False)
        tk.Label(book_frame, text="ORDER BOOK (Yes)", fg=FG_DIM, bg=PANEL,
                 font=FONT_BOLD, anchor="w").pack(fill="x")
        self.book_text = tk.Text(book_frame, height=10, bg=PANEL, fg=FG,
                                 font=FONT_SMALL, relief="flat", highlightthickness=0,
                                 wrap="none", borderwidth=0)
        self.book_text.pack(fill="both", expand=True, pady=(2, 0))
        self.book_text.configure(state="disabled")
        # History sparkline
        tk.Label(right, text="PRICE HISTORY", fg=FG_DIM, bg=PANEL,
                 font=FONT_BOLD, anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.sparkline = Sparkline(right, height=80)
        self.sparkline.pack(fill="x", padx=10, pady=(2, 8))

        # Bottom: trades ticker
        ticker_outer, ticker = make_panel(self, title="RECENT TRADES")
        ticker_outer.pack(fill="x", side="bottom", padx=6, pady=(0, 6))
        self.ticker_text = tk.Text(ticker, height=4, bg=PANEL, fg=FG,
                                   font=FONT_SMALL, relief="flat",
                                   highlightthickness=0, wrap="none", borderwidth=0)
        self.ticker_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.ticker_text.configure(state="disabled")
        # Color tags for ticker
        self.ticker_text.tag_configure("buy", foreground=GREEN)
        self.ticker_text.tag_configure("sell", foreground=RED)
        self.ticker_text.tag_configure("dim", foreground=FG_DIM)

    # ---- Actions ----

    def do_search(self):
        q = self.search_var.get().strip()
        if not q:
            return
        self._set_status(f"searching '{q}'…", YELLOW)
        # Reuse cmd_search by calling our local helper that returns parsed JSON
        self.worker.submit(self._search_helper, {"query": q, "limit": 30}, "search")

    def _search_helper(self, query: str, limit: int):
        # Hits /public-search via PolymarketClient directly.
        from urllib.parse import quote
        data = self.client.get(f"{GAMMA}/public-search?q={quote(query)}")
        return data.get("events", [])

    def refresh_trending(self):
        self._set_status("loading trending…", YELLOW)
        self.worker.submit(self._trending_helper, {"limit": 30}, "trending")

    def _trending_helper(self, limit: int):
        return self.client.get(
            f"{GAMMA}/events?limit={limit}&active=true&closed=false&order=volume&ascending=false"
        )

    def refresh_trades(self):
        if not self.trades_enabled.get():
            return
        self.worker.submit(self._trades_helper, {"limit": 20}, "trades")

    def _trades_helper(self, limit: int):
        return self.client.get(f"{DATA}/trades?limit={limit}")

    def _toggle_trades(self):
        if self.trades_enabled.get():
            self.refresh_trades()
            self.after(self.REFRESH_TRADES_MS, self.refresh_trades)
        # else: no more refreshes scheduled

    def _on_market_select(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.trending_markets):
            return
        slug = self.trending_markets[idx][0]
        if slug == self.selected_slug:
            return
        self.selected_slug = slug
        self._set_status(f"loading {slug}…", YELLOW)
        self.worker.submit(self._quick_helper, {"slug": slug, "depth": 8}, "detail")
        self.worker.submit(self._history_helper, {"slug": slug}, "history")

    def _quick_helper(self, slug: str, depth: int):
        """Build a market-detail snapshot by hitting Gamma + CLOB directly."""
        from urllib.parse import quote
        markets = self.client.get(f"{GAMMA}/markets?slug={quote(slug)}")
        if not markets:
            raise PolymarketError(f"No market found with slug: {slug}")
        m = markets[0]
        import json as _json
        tokens = _json.loads(m.get("clobTokenIds") or "[]")
        outcomes = _json.loads(m.get("outcomes") or "[]")
        if not tokens or len(tokens) < 2:
            raise PolymarketError("Market has no tradable CLOB tokens.")
        snap = {"market": m, "outcomes": []}
        for i, t in enumerate(tokens):
            try:
                buy = self.client.get(f"{CLOB}/price?token_id={t}&side=buy").get("price")
                sell = self.client.get(f"{CLOB}/price?token_id={t}&side=sell").get("price")
                mid = self.client.get(f"{CLOB}/midpoint?token_id={t}").get("mid")
                book = self.client.get(f"{CLOB}/book?token_id={t}")
            except PolymarketError as e:
                snap["outcomes"].append({"outcome": outcomes[i] if i < len(outcomes) else f"Outcome {i}",
                                         "token_id": t, "error": str(e)})
                continue
            snap["outcomes"].append({
                "outcome": outcomes[i] if i < len(outcomes) else f"Outcome {i}",
                "token_id": t,
                "buy": buy, "sell": sell, "mid": mid,
                "last_trade": book.get("last_trade_price"),
                "best_bid": book.get("bids", [{}])[0].get("price") if book.get("bids") else None,
                "best_ask": book.get("asks", [{}])[0].get("price") if book.get("asks") else None,
                "bids": book.get("bids", [])[:depth],
                "asks": book.get("asks", [])[:depth],
            })
        return snap

    def _history_helper(self, slug: str):
        from urllib.parse import quote
        markets = self.client.get(f"{GAMMA}/markets?slug={quote(slug)}")
        if not markets:
            return []
        cid = markets[0].get("conditionId")
        if not cid:
            return []
        data = self.client.get(f"{CLOB}/prices-history?market={cid}&interval=1w&fidelity=80")
        return [(pt["t"], float(pt["p"])) for pt in data.get("history", [])]

    # ---- Result drain (UI thread) ----

    def _drain_results(self):
        try:
            while True:
                tag, value, err = self.results.get_nowait()
                self._handle_result(tag, value, err)
        except queue.Empty:
            pass
        self.after(100, self._drain_results)

    def _handle_result(self, tag, value, err):
        if err:
            self._set_status(f"✗ {err}", RED)
            return
        if tag == "trending":
            self._render_trending(value)
        elif tag == "search":
            self._render_trending(value)  # search returns events; reuse renderer
        elif tag == "detail":
            self._render_detail(value)
        elif tag == "history":
            self.sparkline.plot(value)
            if value:
                self._set_status(f"✓ loaded ({len(value)} history pts)", GREEN)
        elif tag == "trades":
            self._render_trades(value)
            if self.trades_enabled.get():
                self.after(self.REFRESH_TRADES_MS, self.refresh_trades)
        elif tag == "trending":
            # already handled
            pass

    # ---- Renderers ----

    def _render_trending(self, events):
        self.trending_markets = []
        self.listbox.delete(0, "end")
        for evt in events:
            slug = evt.get("slug", "")
            title = evt.get("title", "?")[:50]
            vol = fmt_vol(evt.get("volume", 0))
            label = f"{title}   {vol}"
            self.listbox.insert("end", label)
            self.trending_markets.append((slug, title, vol))
        self._set_status(f"✓ {len(events)} markets", GREEN)
        self.after(self.REFRESH_TRENDING_MS, self.refresh_trending)

    def _render_detail(self, snap):
        m = snap["market"]
        outcomes = snap["outcomes"]
        closed = m.get("closed", False)
        status = "CLOSED" if closed else "ACTIVE"
        vol = fmt_vol(m.get("volume", 0))
        self.header_var.set(
            f"{m.get('question', '?')}\n[{status}]  Volume: {vol}  |  slug: {m.get('slug','')}"
        )
        # Outcomes text
        self.outcomes_text.configure(state="normal")
        self.outcomes_text.delete("1.0", "end")
        for o in outcomes:
            if "error" in o:
                line = f"[{o.get('outcome','?')}]  error: {o['error']}\n"
                self.outcomes_text.insert("end", line)
                continue
            line = (f"[{o['outcome']}]  Buy: {fmt_pct(o.get('buy'))}  "
                    f"Sell: {fmt_pct(o.get('sell'))}  Mid: {fmt_pct(o.get('mid'))}  "
                    f"Last: {fmt_pct(o.get('last_trade'))}\n"
                    f"   best bid {fmt_pct(o.get('best_bid'))}  "
                    f"best ask {fmt_pct(o.get('best_ask'))}\n\n")
            self.outcomes_text.insert("end", line)
        self.outcomes_text.configure(state="disabled")
        # Book text — show first outcome's book
        self.book_text.configure(state="normal")
        self.book_text.delete("1.0", "end")
        first_book = next((o for o in outcomes if "bids" in o), None)
        if first_book:
            self.book_text.insert("end", f"  ASKS  ({first_book['outcome']})\n", "dim")
            for a in reversed(first_book.get("asks", [])[:8]):
                self.book_text.insert("end",
                    f"    {fmt_pct(a['price']):>7}  x{float(a['size']):>10.2f}\n", "sell")
            self.book_text.insert("end", "  ─────────────\n", "dim")
            self.book_text.insert("end", f"  BIDS  ({first_book['outcome']})\n", "dim")
            for b in first_book.get("bids", [])[:8]:
                self.book_text.insert("end",
                    f"    {fmt_pct(b['price']):>7}  x{float(b['size']):>10.2f}\n", "buy")
        else:
            self.book_text.insert("end", "(no book)\n", "dim")
        self.book_text.configure(state="disabled")

    def _render_trades(self, trades):
        self.ticker_text.configure(state="normal")
        self.ticker_text.delete("1.0", "end")
        for t in trades[:20]:
            side = t.get("side", "?")
            tag = "buy" if side == "BUY" else "sell"
            ts = t.get("timestamp", "")
            try:
                ts_short = time.strftime("%H:%M:%S", time.gmtime(int(ts)))
            except Exception:
                ts_short = ""
            line = (f"  {ts_short}  {side:4}  {fmt_pct(t.get('price')):>7}  "
                    f"x{float(t.get('size', 0)):>8.2f}  "
                    f"[{t.get('outcome','?'):>4}]  "
                    f"{(t.get('title','?') or '?')[:55]}\n")
            self.ticker_text.insert("end", line, tag)
        self.ticker_text.configure(state="disabled")

    # ---- Status ----

    def _set_status(self, text: str, color: str = YELLOW):
        self.status_var.set(f"● {text}")


# ---------- CLI entry ----------

def main():
    ap = argparse.ArgumentParser(prog="polymarket-gui",
                                 description="Polymarket dark dashboard (Tkinter).")
    ap.add_argument("--insecure", action="store_true",
                    help="Skip SSL cert verification (use on networks with MITM proxies).")
    args = ap.parse_args()

    try:
        app = Dashboard(insecure=args.insecure)
    except tk.TclError as e:
        print(f"Cannot start GUI: {e}", file=sys.stderr)
        print("Are you running on a system with a display? (Tkinter requires X11/Wayland on Linux, or a desktop session on Windows/macOS.)",
              file=sys.stderr)
        sys.exit(1)
    app.mainloop()


if __name__ == "__main__":
    main()
