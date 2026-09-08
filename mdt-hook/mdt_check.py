#!/usr/bin/env python3
"""
MDT pre-push check — calls the MDT backend to run HMDA drift analysis
on the changed files before every push. Shows a rich terminal report.

If the backend is not reachable, the hook exits 0 (non-blocking) so
developers can still push without a running Docker stack.

Set MDT_FORCE=1 to bypass a HIGH/CRITICAL block.
Set MDT_SKIP=1 to skip the check entirely.
"""
import os
import sys
import json
import subprocess
import urllib.request
import urllib.error

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_URL = os.environ.get("MDT_API_URL", "http://localhost:8000")
FORCE    = os.environ.get("MDT_FORCE", "0") == "1"
SKIP     = os.environ.get("MDT_SKIP",  "0") == "1"

RISK_COLORS = {
    "LOW":      "\033[32m",   # green
    "MEDIUM":   "\033[33m",   # yellow
    "HIGH":     "\033[91m",   # bright red
    "CRITICAL": "\033[31m",   # red
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def _get_changed_files():
    """Return list of files changed since the last push (or HEAD~1)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, check=True
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return files
    except Exception:
        return []


def _get_repo_url():
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        url = result.stdout.strip()
        # Convert SSH to HTTPS if needed
        if url.startswith("git@github.com:"):
            url = "https://github.com/" + url[len("git@github.com:"):]
        return url
    except Exception:
        return ""


def _get_commit_sha():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return "HEAD"


def _call_api(payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{BASE_URL}/analysis/analyze",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _print_report(result):
    level  = (result.get("severity") or "UNKNOWN").upper()
    score  = result.get("risk_score", 0)
    color  = RISK_COLORS.get(level, "")
    svcs   = result.get("impacted_services", [])
    expl   = result.get("explanation", "")
    files  = result.get("affected_files", [])

    print(f"\n{BOLD}━━━ MDT HMDA Pre-push Analysis ━━━{RESET}")
    print(f"  Risk score : {color}{BOLD}{score}/100{RESET}")
    print(f"  Severity   : {color}{BOLD}{level}{RESET}")
    if svcs:
        print(f"  Impacted   : {', '.join(svcs)}")
    if expl:
        print(f"\n  {expl[:300]}{'…' if len(expl) > 300 else ''}")
    if files:
        print(f"\n  Changed files ({len(files)}):")
        for f in files[:8]:
            path = f.get("path", f) if isinstance(f, dict) else f
            print(f"    • {path}")
    print()


def main():
    if SKIP:
        sys.exit(0)

    # Check backend reachability
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=3)
    except Exception:
        print(f"MDT: backend not reachable at {BASE_URL} — skipping pre-push check")
        sys.exit(0)

    changed_files = _get_changed_files()
    if not changed_files:
        print("MDT: no changed files detected — skipping analysis")
        sys.exit(0)

    repo_url   = _get_repo_url()
    commit_sha = _get_commit_sha()

    print(f"MDT: analysing {len(changed_files)} changed file(s)…")

    try:
        result = _call_api({
            "repo_url":     repo_url or "https://github.com/kartick026/MDT",
            "commit_sha":   commit_sha,
            "changed_files": changed_files,
        })
    except Exception as exc:
        print(f"MDT: analysis failed ({exc}) — allowing push")
        sys.exit(0)

    _print_report(result)

    level = (result.get("severity") or "LOW").upper()
    if level in ("HIGH", "CRITICAL") and not FORCE:
        print(f"MDT: push {BOLD}blocked{RESET} — risk is {RISK_COLORS.get(level,'')}{level}{RESET}.")
        print(f"     Fix the issues above or run:  MDT_FORCE=1 git push")
        sys.exit(1)

    print(f"MDT: ✓ push approved (risk = {level})")
    sys.exit(0)


if __name__ == "__main__":
    main()
