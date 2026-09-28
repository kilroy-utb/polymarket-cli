#!/usr/bin/env bash
# Smoke test — hit each endpoint once to confirm everything still works.
# Run: ./test_smoke.sh
# Exit 0 = all pass, non-zero = at least one failed.

set -e

cd "$(dirname "$0")"

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS  $name"
        PASS=$((PASS+1))
    else
        echo "  FAIL  $name  ($*)"
        FAIL=$((FAIL+1))
    fi
}

echo "Smoke testing polymarket CLI..."
echo

check "Gamma: trending"           python3 polymarket.py trending --limit 3
check "Gamma: search 'bitcoin'"   python3 polymarket.py search "bitcoin" --limit 2
check "Gamma: market by slug"     python3 polymarket.py market will-jd-vance-win-the-2028-us-presidential-election
check "Gamma: event by slug"      python3 polymarket.py event democratic-presidential-nominee-2028
check "CLOB: price"               python3 polymarket.py price 16040015440196279900485035793550429453516625694844857319147506590755961451627
check "CLOB: book"                python3 polymarket.py book 16040015440196279900485035793550429453516625694844857319147506590755961451627 --depth 3
check "CLOB: history"             python3 polymarket.py history 0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422 --interval 1w --fidelity 10
check "Data: trades"              python3 polymarket.py trades --limit 5
check "Combo: token snapshot"     python3 polymarket.py token 16040015440196279900485035793550429453516625694844857319147506590755961451627
check "Combo: quick market"       python3 polymarket.py quick will-jd-vance-win-the-2028-us-presidential-election --depth 2
check "JSON output"               python3 polymarket.py trending --limit 1 --json

echo
echo "  $PASS passed, $FAIL failed"
exit $FAIL
