#!/usr/bin/env bash
# Polymarket CLI — bootstrap script.
# - Checks Python version
# - Confirms stdlib is intact
# - Runs smoke test with diagnostic output on failure
# - Optionally symlinks to /usr/local/bin
#
# Usage:
#   ./setup.sh              # check + smoke test
#   ./setup.sh --install    # also symlink to /usr/local/bin/polymarket
#   ./setup.sh --no-test    # skip smoke test

set -e

cd "$(dirname "$0")"

INSTALL=0
SKIP_TEST=0
for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=1 ;;
        --no-test) SKIP_TEST=1 ;;
        -h|--help)
            echo "Usage: $0 [--install] [--no-test]"
            echo "  --install   symlink to /usr/local/bin/polymarket"
            echo "  --no-test   skip smoke test"
            exit 0
            ;;
    esac
done

# ---------- 1. Python version ----------
echo "== Python check =="
if ! command -v python3 >/dev/null 2>&1; then
    echo "  FAIL  python3 not found on PATH"
    echo "        Install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')

echo "  Found python3 $PY_VERSION"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
    echo "  FAIL  Python 3.8+ required (you have $PY_VERSION)"
    exit 1
fi
echo "  PASS  Python $PY_VERSION meets requirement (3.8+)"

# ---------- 2. stdlib modules ----------
echo
echo "== stdlib check =="
MISSING=0
for mod in urllib.request urllib.parse urllib.error json argparse datetime; do
    if python3 -c "import $mod" 2>/dev/null; then
        echo "  PASS  $mod"
    else
        echo "  FAIL  $mod  (should be in stdlib — your Python install may be broken)"
        MISSING=1
    fi
done
if [ "$MISSING" -ne 0 ]; then
    echo "  Reinstall Python: https://www.python.org/downloads/"
    exit 1
fi

# ---------- 3. CLI file check ----------
echo
echo "== file check =="
for f in polymarket.py test_smoke.sh; do
    if [ -f "$f" ]; then
        echo "  PASS  $f present"
    else
        echo "  FAIL  $f missing — re-clone the repo"
        exit 1
    fi
done
chmod +x polymarket.py test_smoke.sh
echo "  PASS  executable bit set"

# ---------- 4. Network sanity ----------
echo
echo "== network check =="
for url in \
    "https://gamma-api.polymarket.com/events?limit=1" \
    "https://clob.polymarket.com/markets?limit=1" \
    "https://data-api.polymarket.com/trades?limit=1"; do
    host=$(echo "$url" | sed -E 's|https?://([^/]+).*|\1|')
    code=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "$url" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
        echo "  PASS  $host ($code)"
    elif [ "$code" = "000" ]; then
        echo "  FAIL  $host unreachable (timeout / DNS / firewall)"
    else
        echo "  WARN  $host returned HTTP $code (may be transient)"
    fi
done

# ---------- 5. Smoke test ----------
if [ "$SKIP_TEST" -ne 1 ]; then
    echo
    echo "== smoke test =="
    bash test_smoke.sh
    SMOKE_EXIT=$?
    if [ "$SMOKE_EXIT" -ne 0 ]; then
        echo
        echo "Smoke test failed (exit $SMOKE_EXIT)."
        echo "Re-run any failing command directly for full error output:"
        echo "  python3 polymarket.py trades --limit 5"
        echo "If it's a Data API timeout, retry — the endpoint occasionally hangs."
        exit $SMOKE_EXIT
    fi
fi

# ---------- 6. Install (optional) ----------
if [ "$INSTALL" -eq 1 ]; then
    echo
    echo "== install =="
    TARGET="/usr/local/bin/polymarket"
    if [ -w "/usr/local/bin" ] || command -v sudo >/dev/null 2>&1; then
        if command -v sudo >/dev/null 2>&1 && [ ! -w "/usr/local/bin" ]; then
            sudo ln -sf "$(pwd)/polymarket.py" "$TARGET"
        else
            ln -sf "$(pwd)/polymarket.py" "$TARGET"
        fi
        if command -v polymarket >/dev/null 2>&1; then
            echo "  PASS  installed to $TARGET"
            echo "         now you can run:  polymarket trending --limit 5"
        else
            echo "  FAIL  install failed"
            exit 1
        fi
    else
        echo "  SKIP  /usr/local/bin not writable and no sudo — install manually:"
        echo "         ln -sf \"\$(pwd)/polymarket.py\" /usr/local/bin/polymarket"
    fi
fi

echo
echo "All checks passed. Try:"
echo "  python3 polymarket.py trending --limit 5"
echo "  python3 polymarket.py search \"bitcoin\""
