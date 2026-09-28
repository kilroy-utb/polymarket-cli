#!/usr/bin/env bash
# Smoke test — hit each endpoint once to confirm everything still works.
# Run: ./test_smoke.sh
# Exit 0 = all pass, non-zero = at least one failed.
#
# Each command gets up to 3 attempts (slow endpoints occasionally time out).

cd "$(dirname "$0")"

PASS=0
FAIL=0
ATTEMPTS=3

check() {
    local name="$1"
    shift
    local i=1
    while [ "$i" -le "$ATTEMPTS" ]; do
        if "$@" >/dev/null 2>&1; then
            echo "  PASS  $name"
            PASS=$((PASS+1))
            return 0
        fi
        i=$((i+1))
    done
    echo "  FAIL  $name  (tried $ATTEMPTS times: $*)"
    FAIL=$((FAIL+1))
    return 0   # never propagate failure up — we tally ourselves
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

# If any check failed, retry everything with --insecure.
# The previous SSL-only probe didn't catch networks where the proxy
# returns 404 for filtered endpoints but works with --insecure.
if [ "$FAIL" -gt 0 ]; then
    echo
    echo "Re-running all checks with --insecure (handles SSL issues and proxy filters)..."
    echo
    PASS=0; FAIL=0
    check "Gamma: trending"           python3 polymarket.py --insecure trending --limit 3
    check "Gamma: search 'bitcoin'"   python3 polymarket.py --insecure search "bitcoin" --limit 2
    check "Gamma: market by slug"     python3 polymarket.py --insecure market will-jd-vance-win-the-2028-us-presidential-election
    check "Gamma: event by slug"      python3 polymarket.py --insecure event democratic-presidential-nominee-2028
    check "CLOB: price"               python3 polymarket.py --insecure price 16040015440196279900485035793550429453516625694844857319147506590755961451627
    check "CLOB: book"                python3 polymarket.py --insecure book 16040015440196279900485035793550429453516625694844857319147506590755961451627 --depth 3
    check "CLOB: history"             python3 polymarket.py --insecure history 0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422 --interval 1w --fidelity 10
    check "Data: trades"              python3 polymarket.py --insecure trades --limit 5
    check "Combo: token snapshot"     python3 polymarket.py --insecure token 16040015440196279900485035793550429453516625694844857319147506590755961451627
    check "Combo: quick market"       python3 polymarket.py --insecure quick will-jd-vance-win-the-2028-us-presidential-election --depth 2
    check "JSON output"               python3 polymarket.py --insecure trending --limit 1 --json
fi

echo
echo "  $PASS passed, $FAIL failed"
exit $FAIL
