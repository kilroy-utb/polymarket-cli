#!/usr/bin/env bash
# Diagnostic probe — shows which polymarket CLI commands actually work
# in your current network environment.
#
# This is more honest than the full smoke test: instead of all-or-nothing
# PASS/FAIL, it runs every command once and tells you what each one got.
# Use this when the full smoke test fails but you want to know which
# endpoints are usable.
#
# Usage:
#   ./probe.sh            # default: with --insecure (recommended)
#   ./probe.sh --secure   # force SSL verification
#   ./probe.sh --json     # machine-readable output

set -u

cd "$(dirname "$0")"

# Default to --insecure. Many corporate / restricted networks MITM the
# Gamma host specifically (and only Gamma), so a secure client always
# fails there. Use --secure to force verification.
EXTRA_ARGS=(--insecure)
JSON=0
for arg in "$@"; do
    case "$arg" in
        --insecure) ;;  # already on
        --secure) EXTRA_ARGS=() ;;
        --json) JSON=1 ;;
    esac
done

# Each probe: name | cmd | expected_keys (rough check on response shape)
TOKEN_ID="16040015440196279900485035793550429453516625694844857319147506590755961451627"
CONDITION_ID="0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422"
MARKET_SLUG="will-jd-vance-win-the-2028-us-presidential-election"
EVENT_SLUG="democratic-presidential-nominee-2028"

run_one() {
    local name="$1"
    shift
    local t0 t1 status elapsed out_file
    out_file=$(mktemp)
    t0=$(date +%s.%N)
    if "$@" >"$out_file" 2>&1; then
        status="PASS"
    else
        rc=$?
        # Exit code 1 = our error path. Anything else is unexpected.
        status="FAIL(rc=$rc)"
    fi
    t1=$(date +%s.%N)
    elapsed=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.1f", b - a }')
    # Extract first non-empty, non-blank line of stderr/stdout for hint
    local hint
    hint=$(grep -m1 -E 'SSL certificate|Cloudflare|Network blocked|HTTP [0-9]+:|Connection error|No .* found' "$out_file" 2>/dev/null \
           | head -c 100 \
           | tr '\n' ' ' \
           | sed 's/  */ /g')
    if [ -z "$hint" ]; then
        hint=$(head -1 "$out_file" | head -c 80)
    fi
    rm -f "$out_file"
    if [ "$JSON" -eq 1 ]; then
        printf '{"name":"%s","status":"%s","elapsed_s":%s,"hint":"%s"}\n' \
            "$(echo "$name" | sed 's/"/\\"/g')" "$status" "$elapsed" "$(echo "$hint" | sed 's/"/\\"/g')"
    else
        printf "  %-32s  %-12s  %5ss   %s\n" "$name" "$status" "$elapsed" "$hint"
    fi
}

if [ "$JSON" -eq 0 ]; then
    echo "Probing polymarket CLI against your current network..."
    if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
        echo "  (default mode with --insecure — most corporate networks need this for Gamma)"
        echo "  (use --secure to test without SSL bypass)"
    else
        echo "  (secure mode — no SSL bypass)"
    fi
    echo
    printf "  %-32s  %-12s  %7s   %s\n" "COMMAND" "STATUS" "TIME" "FIRST HINT"
    echo "  ------------------------------  ------------  -------   ----------------------------------------"
fi

# Gamma API
run_one "Gamma: search bitcoin"      python3 polymarket.py "${EXTRA_ARGS[@]}" search "bitcoin" --limit 2
run_one "Gamma: trending"            python3 polymarket.py "${EXTRA_ARGS[@]}" trending --limit 3
run_one "Gamma: market <slug>"       python3 polymarket.py "${EXTRA_ARGS[@]}" market "$MARKET_SLUG"
run_one "Gamma: event <slug>"        python3 polymarket.py "${EXTRA_ARGS[@]}" event "$EVENT_SLUG"

# CLOB API
run_one "CLOB: price"                python3 polymarket.py "${EXTRA_ARGS[@]}" price "$TOKEN_ID"
run_one "CLOB: book"                 python3 polymarket.py "${EXTRA_ARGS[@]}" book "$TOKEN_ID" --depth 3
run_one "CLOB: history"              python3 polymarket.py "${EXTRA_ARGS[@]}" history "$CONDITION_ID" --interval 1w --fidelity 10

# Data API
run_one "Data: trades"               python3 polymarket.py "${EXTRA_ARGS[@]}" trades --limit 5

# Combo
run_one "Combo: token snapshot"      python3 polymarket.py "${EXTRA_ARGS[@]}" token "$TOKEN_ID"
run_one "Combo: quick market"        python3 polymarket.py "${EXTRA_ARGS[@]}" quick "$MARKET_SLUG" --depth 2

if [ "$JSON" -eq 0 ]; then
    echo
    echo "Tip:"
    echo "  - PASS = real data came back, that endpoint is usable"
    echo "  - FAIL with 'SSL certificate' = your network MITMs HTTPS, add --insecure"
    echo "  - FAIL with 'Network blocked' = proxy/firewall blocks the host, no CLI-side fix"
    echo "  - FAIL with 'HTTP 4xx/5xx' = endpoint responded with an error, retry or check API"
    echo
    echo "If everything passes except 'Data: trades', that's typical for networks that"
    echo "block Data API specifically (gambling/crypto category)."
fi
