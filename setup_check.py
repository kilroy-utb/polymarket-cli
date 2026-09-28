#!/usr/bin/env python3
"""Diagnostic checks for polymarket-cli setup.

Run by setup.sh. Exits 0 if everything looks good, non-zero otherwise.
All the actual checking happens here so the bash side stays minimal
and works under bash / zsh / dash / Git Bash.
"""
import sys
import os
import shutil
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


def check_network() -> bool:
    header("network check")
    hosts = [
        "https://gamma-api.polymarket.com/events?limit=1",
        "https://clob.polymarket.com/markets?limit=1",
        "https://data-api.polymarket.com/trades?limit=1",
    ]
    fails = 0
    for url in hosts:
        host = url.split("/")[2]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "polymarket-cli-setup"})
            with urllib.request.urlopen(req, timeout=10) as r:
                ok(f"{host} (HTTP {r.status})")
        except urllib.error.HTTPError as e:
            warn(f"{host} HTTP {e.code} (endpoint responding, may be rate-limited)")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            fail(f"{host} — {reason}")
            fails += 1

    if fails == len(hosts):
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
