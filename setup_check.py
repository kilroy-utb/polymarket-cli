#!/usr/bin/env python3
"""Diagnostic checks for polymarket-cli setup.

Run by setup.sh. Exits 0 if everything looks good, non-zero otherwise.
All the actual checking happens here so the bash side stays minimal
and works under bash / zsh / dash / Git Bash.
"""
import sys
import os
import shutil
import ssl
import urllib.request
import urllib.error


def header(title: str) -> None:
    print()
    print(f"== {title} ==")


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def warn(msg: str) -> None:
    print(f"  WARN  {msg}")


def check_python() -> bool:
    header("Python check")
    py = shutil.which("python3")
    if not py:
        fail("python3 not found on PATH")
        print("        Install Python 3.10+ from https://www.python.org/downloads/")
        return False
    print(f"  Found python3 {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}")
    if sys.version_info < (3, 8):
        fail(f"Python 3.8+ required (you have {sys.version_info[0]}.{sys.version_info[1]})")
        return False
    ok(f"Python {sys.version_info[0]}.{sys.version_info[1]} meets requirement (3.8+)")
    return True


def check_stdlib() -> bool:
    header("stdlib check")
    mods = ["urllib.request", "urllib.parse", "urllib.error", "json", "argparse", "datetime"]
    all_ok = True
    for m in mods:
        try:
            __import__(m)
            ok(m)
        except ImportError:
            fail(f"{m} (should be in stdlib — your Python install may be broken)")
            all_ok = False
    if not all_ok:
        print("  Reinstall Python: https://www.python.org/downloads/")
    return all_ok


def check_files() -> bool:
    header("file check")
    here = os.path.dirname(os.path.abspath(__file__))
    all_ok = True
    for f in ["polymarket.py", "test_smoke.sh"]:
        path = os.path.join(here, f)
        if os.path.isfile(path):
            ok(f"{f} present")
        else:
            fail(f"{f} missing — re-clone the repo")
            all_ok = False
    return all_ok


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def check_network() -> bool:
    header("network check")
    hosts = [
        "https://gamma-api.polymarket.com/events?limit=1",
        "https://clob.polymarket.com/markets?limit=1",
        "https://data-api.polymarket.com/trades?limit=1",
    ]
    fails = 0
    ssl_failures = 0
    cf_failures = 0
    for url in hosts:
        host = url.split("/")[2]
        ctx = None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                ok(f"{host} (HTTP {r.status})")
        except urllib.error.HTTPError as e:
            reason_body = e.read().decode(errors="replace")[:200]
            if "1010" in reason_body:
                fail(f"{host} — Cloudflare browser integrity check (1010)")
                cf_failures += 1
            else:
                warn(f"{host} HTTP {e.code} (endpoint responding, may be rate-limited)")
            fails += 1
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            reason_s = str(reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason_s or "certificate verify failed" in reason_s.lower():
                fail(f"{host} — SSL cert verify failed (likely MITM/proxy on your network)")
                ssl_failures += 1
            else:
                fail(f"{host} — {reason}")
            fails += 1

    if fails == len(hosts):
        if cf_failures > 0:
            print()
            print("All three hosts failed with Cloudflare error 1010 (browser integrity check).")
            print("This means Cloudflare is rejecting the User-Agent the script uses.")
            print("This shouldn't happen with the default UA — file a bug.")
        elif ssl_failures > 0:
            print()
            print("All three hosts failed with SSL certificate errors.")
            print("This usually means a corporate proxy / VPN / MITM tool is intercepting HTTPS.")
            print()
            print("Options:")
            print("  1. Use --insecure on every command:")
            print("       python3 polymarket.py trades --insecure --limit 5")
            print("  2. Or set POLYMARKET_INSECURE=1 in your environment.")
            print("  3. Or add your proxy's CA cert to Python's cert store:")
            print("       pip install --upgrade certifi")
        else:
            print()
            print("All three hosts unreachable. Common causes:")
            print("  - Corporate / school firewall blocking outbound HTTPS")
            print("  - VPN required for this network")
            print("  - DNS misconfigured")
            print()
            print("Try opening https://gamma-api.polymarket.com in a browser.")
            print("If the browser works but this fails, you likely need a proxy.")
        return False
    return True


def main() -> int:
    checks = [check_python, check_stdlib, check_files, check_network]
    failed = 0
    for c in checks:
        if not c():
            failed += 1
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
