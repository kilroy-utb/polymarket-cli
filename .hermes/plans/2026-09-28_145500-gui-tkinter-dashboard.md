# Plan: Polymarket Tkinter GUI Dashboard

## Goal

Build a local dark-themed Tkinter desktop GUI that wraps the existing read-only CLI to help the user watch prediction-market movements at a glance.

## Context

- Repo: `/opt/data/polymarket-cli` — already has a working CLI (11 commands across Gamma / CLOB / Data API).
- User environment: Windows + Python 3.9.16, runs into intermittent proxy filtering but most commands work when invoked directly via `python3 polymarket.py ...`.
- Refactor A already extracted `PolymarketClient` and `cmd_*` functions; the GUI will reuse these.

## Approach

Single-file Tkinter app (`gui.py`) that:

1. Imports `PolymarketClient` and the `cmd_*` functions from `polymarket.py`.
2. Renders a dark dashboard with:
   - **Top bar** — search input, refresh button, status indicator (green/yellow/red)
   - **Left panel** — trending markets list (auto-refresh every 30s)
   - **Center panel** — selected market's order book + price history (sparkline)
   - **Bottom panel** — recent trades ticker (last 20, scrolling)
3. Runs network calls on a background thread so the UI never freezes.
4. Dark theme via `ttk.Style` + custom colors (no external theme files needed).

## Why Tkinter (not Qt / web)

- Stdlib only — same constraint as the CLI.
- Single-file `.py`, easy to ship alongside `polymarket.py`.
- No build step, no electron bundle.
- 3.9 compatibility already proven (CLI works there).

## Step-by-step plan

### 1. Skeleton + dark theme

- `gui.py` imports `PolymarketClient` from `polymarket.py`.
- Root window, dark background (`#0e1117` / `#1a1f2b` panels).
- `ttk.Style()` configured with `.` (default) theme overridden to match dark palette.
- Status bar + main split layout (paned window: left list / right detail).

### 2. Search + trending panel

- Search entry → on Enter, run `cmd_search` in a worker thread, populate listbox with `slug` + `question` + `volume`.
- "Trending" tab fetches `cmd_trending` on load and on a 30s `root.after` timer.
- Selecting a market triggers `cmd_quick` for the right panel.

### 3. Market detail panel

- Two columns:
  - **Top**: header (question, status, volume) + outcomes list (Yes / No + price + book mid).
  - **Bottom**: order book (bids green / asks red) + sparkline of price history (`cmd_history`).

### 4. Recent trades ticker

- Bottom horizontal strip, polling `cmd_trades` every 10s.
- Auto-scroll newest left, oldest fall off.
- Color-code BUY green / SELL red.

### 5. Threading model

- One `threading.Thread` worker that consumes jobs from a `queue.Queue`.
- Worker pulls `(callback, args)` tuples, calls the cmd function, puts result on a `result_queue`.
- Tk `root.after(100, drain_queue)` polls result_queue and updates widgets on the main thread.
- All `cmd_*` functions already call `sys.exit(1)` on error — for GUI we'll wrap them so errors land on the queue instead.

### 6. Packaging

- `python3 gui.py` to run.
- Add `gui` target to README and to `aliases.sh`.
- Update `setup.sh` to check tkinter import (`python3 -c "import tkinter"`).

## Files likely to change

- **NEW** `gui.py` — main GUI file (~400-500 lines).
- **MODIFY** `polymarket.py` — refactor `cmd_*` to return instead of `sys.exit(1)`, so the GUI can catch errors. Backward-compatible: CLI mode still exits on error.
- **MODIFY** `aliases.sh` — add `pmgui`.
- **MODIFY** `README.md` — add GUI section + screenshot placeholder.
- **MODIFY** `setup.sh` — add tkinter availability check.

## Tests / validation

- `python3 gui.py` opens a window with the dark theme.
- Search for "bitcoin" populates the listbox within ~1s.
- Selecting a market populates the right panel within ~2s.
- Trades ticker updates every 10s without UI freeze.
- Kill network → status indicator goes red, no crash.
- Run on Windows Python 3.9 (the user's actual env).

## Risks / tradeoffs

- **Tkinter looks dated** — but it's the path of least resistance for stdlib GUI. If user dislikes the look later, swap to PyQt or web stack.
- **Tkinter on Windows** — bundled with Python so no extra install. Some styling quirks but dark theme is achievable with `ttk.Style`.
- **Threading + sys.exit** — `cmd_*` functions exit on error, which would kill the GUI process. Must refactor to raise instead.
- **Proxy filtering** — same issue as CLI. Will integrate `--insecure` flag and `POLYMARKET_INSECURE` env var into the GUI's client construction.

## Open questions

- Should the GUI support search-as-you-type or only on Enter?
- Should trades ticker be always-on or toggleable?
- Do we want chart drawing (sparkline) in pure Tkinter (Canvas) or external lib (matplotlib)? Pure Canvas keeps zero deps.
