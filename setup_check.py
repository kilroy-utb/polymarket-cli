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


def _probe(url: str, ctx):
    """Try one request; return (status, body) on HTTPError, or raise on URL error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=10, context=ctx)


def check_network() -> bool:
    header("network check")
    hosts = [
        "https://gamma-api.polymarket.com/events?limit=1",
        "https://clob.polymarket.com/markets?limit=1",
        "https://data-api.polymarket.com/trades?limit=1",
    ]
    real_failures = 0
    mitm_detected = False
    unverified_ctx = ssl._create_unverified_context()

    for url in hosts:
        host = url.split("/")[2]
        try:
            with _probe(url, None) as r:
                ok(f"{host} (HTTP {r.status})")
                continue
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            if "1010" in body:
                warn(f"{host} — Cloudflare browser integrity check (1010) — endpoint up, just blocked our UA")
            elif "blocked" in body.lower() or "封鎖" in body or "<html" in body.lower():
                warn(f"{host} HTTP {e.code} — proxy returned block page")
            else:
                # 404 / 403 / 5xx — proxy is responding, the endpoint itself
                # might be filtered, but we got a real HTTP response.
                warn(f"{host} HTTP {e.code} — endpoint may be filtered, but network is reachable")
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason_s = str(getattr(e, "reason", e))
            if "CERTIFICATE_VERIFY_FAILED" in reason_s or "certificate verify failed" in reason_s.lower():
                mitm_detected = True
                try:
                    with _probe(url, unverified_ctx) as r:
                        warn(f"{host} — SSL verify failed, but reachable with --insecure (HTTP {r.status})")
                except urllib.error.HTTPError as retry_http:
                    warn(f"{host} HTTP {retry_http.code} with --insecure — endpoint may be filtered, network reachable")
                except Exception as retry_err:
                    fail(f"{host} — SSL cert verify failed AND unreachable with --insecure ({type(retry_err).__name__}: {str(retry_err)[:200]})")
                    real_failures += 1
            else:
                fail(f"{host} — {reason_s}")
                real_failures += 1

    # Only real network failures (timeout / DNS / unreachable) cause hard fail.
    # Any HTTP response (including 4xx / 5xx / 1010) counts as reachable —
    # the smoke test will tell us if the actual API calls work.
    if real_failures == 0:
        if mitm_detected:
            print()
            print("Note: your network appears to MITM HTTPS (corporate proxy / VPN / inspection tool).")
            print("Some hosts needed --insecure to reach. To use the CLI normally, run commands with:")
            print("  python3 polymarket.py <command> --insecure")
            print("Or set POLYMARKET_INSECURE=1 in your shell rc.")
        return True

    print()
    print(f"{real_failures} host(s) unreachable. Check firewall / DNS / VPN.")
    return False


def main() -> int:
    checks = [check_python, check_stdlib, check_files, check_network]
    failed = 0
    for c in checks:
        if not c():
            failed += 1
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
