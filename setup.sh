#!/usr/bin/env bash
# Polymarket CLI — bootstrap script.
#
# Most of the actual logic lives in setup_check.py so the bash side stays
# minimal (works under bash / zsh / dash / Git Bash).
#
# Usage:
#   ./setup.sh              # check + smoke test
#   ./setup.sh --install    # also symlink to /usr/local/bin/polymarket
#   ./setup.sh --no-test    # skip smoke test

cd "$(dirname "$0")"

INSTALL=0
SKIP_TEST=0
for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=1 ;;
        --no-test) SKIP_TEST=1 ;;
        -h|--help)
            echo "Usage: $0 [--install] [--no-test]"
            exit 0
            ;;
    esac
done

# ---------- Run the diagnostic in Python (avoid shell quirks) ----------
python3 setup_check.py
if [ $? -ne 0 ]; then
    echo
    echo "Setup check failed. See messages above."
    exit 1
fi

# ---------- Make sure the script is executable ----------
chmod +x polymarket.py test_smoke.sh 2>/dev/null || true

# ---------- Smoke test ----------
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
        exit $SMOKE_EXIT
    fi
fi

# ---------- Optional install ----------
if [ "$INSTALL" -eq 1 ]; then
    echo
    echo "== install =="
    TARGET="/usr/local/bin/polymarket"
    if [ -w "/usr/local/bin" ] 2>/dev/null; then
        ln -sf "$(pwd)/polymarket.py" "$TARGET"
    elif command -v sudo >/dev/null 2>&1; then
        sudo ln -sf "$(pwd)/polymarket.py" "$TARGET"
    else
        echo "  SKIP  /usr/local/bin not writable and no sudo"
        exit 0
    fi
    if command -v polymarket >/dev/null 2>&1; then
        echo "  PASS  installed to $TARGET"
        echo "         now you can run:  polymarket trending --limit 5"
    else
        echo "  FAIL  install failed"
        exit 1
    fi
fi

echo
echo "All checks passed. Try:"
echo "  python3 polymarket.py trending --limit 5"
echo "  python3 polymarket.py search \"bitcoin\""
