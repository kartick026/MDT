#!/usr/bin/env python3
"""
MDT HMDA Drift Analysis Tool & Git Hook

Runs HMDA (Hierarchical Microservice Drift Analysis) against changed files.
Can be used:
1. Interactively before committing:
     python mdt-hook/mdt_check.py --staged    # Check files staged via `git add`
     python mdt-hook/mdt_check.py --working   # Check all modified working files
     python mdt-hook/mdt_check.py path/to/file.py  # Check specific files
     python mdt-hook/mdt_check.py --dry-run   # Preview score without blocking

2. As a Git hook:
     .git/hooks/pre-commit (blocks commit if HMDA risk is HIGH/CRITICAL)
     .git/hooks/pre-push   (blocks push if HMDA risk is HIGH/CRITICAL)

Set MDT_FORCE=1 to bypass a HIGH/CRITICAL block.
Set MDT_SKIP=1 to skip the check entirely.
Set MDT_API_URL to point to a custom backend (default: http://localhost:8000).
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if isinstance(_stream, io.TextIOWrapper):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

BASE_URL = os.environ.get("MDT_API_URL", "http://localhost:8000").rstrip("/")
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


def _run_git(args):
    try:
        res = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, check=True
        )
        return res.stdout.strip()
    except Exception:
        return ""


def _get_staged_files():
    """Return files currently staged with `git add`."""
    out = _run_git(["diff", "--cached", "--name-only"])
    return [f.strip() for f in out.splitlines() if f.strip()]


def _get_working_files():
    """Return all modified or added files compared to HEAD."""
    out = _run_git(["diff", "--name-only", "HEAD"])
    return [f.strip() for f in out.splitlines() if f.strip()]


def _get_last_commit_files():
    """Return files modified in the most recent commit (HEAD~1..HEAD)."""
    out = _run_git(["diff", "--name-only", "HEAD~1", "HEAD"])
    return [f.strip() for f in out.splitlines() if f.strip()]


def _get_repo_url():
    url = _run_git(["remote", "get-url", "origin"])
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:"):]
    if not url:
        # Fallback to backend project context if local git remote is missing
        try:
            req = urllib.request.Request(f"{BASE_URL}/registry/context")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                url = data.get("repo_url", "")
        except Exception:
            pass
    return url or "https://github.com/kartick026/MDT"


def _get_commit_sha():
    sha = _run_git(["rev-parse", "HEAD"])
    return sha or "HEAD"


def _call_api(payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/analysis/analyze",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _print_report(result, context_title="MDT HMDA Pre-Check Analysis"):
    level = (result.get("severity") or "UNKNOWN").upper()
    score = result.get("risk_score", 0)
    color = RISK_COLORS.get(level, "")
    svcs  = result.get("impacted_services", [])
    expl  = result.get("explanation", "")
    files = result.get("affected_files", [])

    print(f"\n{BOLD}━━━ {context_title} ━━━{RESET}")
    print(f"  Risk score : {color}{BOLD}{score}/100{RESET}")
    print(f"  Severity   : {color}{BOLD}{level}{RESET}")
    if svcs:
        print(f"  Impacted   : {', '.join(svcs)}")
    if expl:
        print(f"\n  {expl[:300]}{'…' if len(expl) > 300 else ''}")
    if files:
        print(f"\n  Changed files evaluated ({len(files)}):")
        for f in files[:8]:
            path = f.get("path", f) if isinstance(f, dict) else f
            print(f"    • {path}")
        if len(files) > 8:
            print(f"    … and {len(files) - 8} more")
    print()


def _install_hook(hook_type: str):
    git_dir = _run_git(["rev-parse", "--git-dir"])
    if not git_dir:
        print("MDT Error: Not inside a git repository.")
        sys.exit(1)
    
    target_hook = Path(git_dir) / "hooks" / hook_type
    target_hook.parent.mkdir(parents=True, exist_ok=True)

    script_path = Path(__file__).resolve()
    # Write a wrapper script for the hook
    content = (
        f'#!/usr/bin/env bash\n'
        f'# MDT {hook_type} hook\n'
        f'exec python3 "{script_path}" --{"staged" if hook_type == "pre-commit" else "pre-push"}\n'
    )

    with open(target_hook, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    
    try:
        os.chmod(target_hook, 0o755)
    except Exception:
        pass

    print(f"{BOLD}✓ MDT {hook_type} hook installed successfully at {target_hook}{RESET}")
    print(f"  It will automatically run HMDA analysis on {hook_type} events.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="MDT HMDA Drift Analysis — Test and evaluate architectural risk before committing or pushing."
    )
    parser.add_argument("files", nargs="*", help="Specific file paths to analyze")
    parser.add_argument("-s", "--staged", action="store_true", help="Analyze files currently staged for commit (git diff --cached)")
    parser.add_argument("-w", "--working", action="store_true", help="Analyze all working tree files (staged & unstaged vs HEAD)")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Preview HMDA score without exiting with error even if HIGH/CRITICAL")
    parser.add_argument("--pre-commit", action="store_true", help="Run in pre-commit hook mode (evaluates staged changes)")
    parser.add_argument("--pre-push", action="store_true", help="Run in pre-push hook mode (evaluates last commit)")
    parser.add_argument("--install-hook", choices=["pre-commit", "pre-push"], help="Install MDT as a local git hook")

    args = parser.parse_args()

    if args.install_hook:
        _install_hook(args.install_hook)

    if SKIP:
        sys.exit(0)

    # Check backend reachability
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=3)
    except Exception:
        print(f"MDT: backend not reachable at {BASE_URL} — skipping HMDA check")
        sys.exit(0)

    # Determine files to analyze
    context_title = "MDT HMDA Analysis"
    if args.files:
        changed_files = args.files
        context_title = "MDT HMDA File Analysis (Manual Preview)"
    elif args.staged or args.pre_commit:
        changed_files = _get_staged_files()
        context_title = "MDT HMDA Pre-Commit Analysis (Staged Files)"
    elif args.working:
        changed_files = _get_working_files()
        context_title = "MDT HMDA Working Tree Analysis (Uncommitted Changes)"
    elif args.pre_push:
        changed_files = _get_last_commit_files()
        context_title = "MDT HMDA Pre-Push Analysis (Last Commit)"
    else:
        # Smart auto-detection when run manually in terminal without flags:
        # 1. Check staged files first
        changed_files = _get_staged_files()
        if changed_files:
            context_title = "MDT HMDA Analysis (Staged Changes)"
        else:
            # 2. Check uncommitted working tree changes
            changed_files = _get_working_files()
            if changed_files:
                context_title = "MDT HMDA Analysis (Working Tree Changes)"
            else:
                # 3. Fallback to last commit
                changed_files = _get_last_commit_files()
                context_title = "MDT HMDA Analysis (Last Commit)"

    if not changed_files:
        print("MDT: No changed files detected to analyze.")
        sys.exit(0)

    repo_url   = _get_repo_url()
    commit_sha = _get_commit_sha()

    print(f"MDT: Analysing {len(changed_files)} file(s) against HMDA model…")

    try:
        result = _call_api({
            "repo_url":      repo_url,
            "commit_sha":    commit_sha,
            "changed_files": changed_files,
        })
    except Exception as exc:
        print(f"MDT: Analysis failed ({exc}) — skipping check")
        sys.exit(0)

    _print_report(result, context_title=context_title)

    level = (result.get("severity") or "LOW").upper()
    score = result.get("risk_score", 0.0)

    # If running in dry-run / manual test preview mode, do not block
    is_interactive_preview = args.dry_run or (not args.pre_commit and not args.pre_push and sys.stdin.isatty())

    if level in ("HIGH", "CRITICAL"):
        if is_interactive_preview and not (args.pre_commit or args.pre_push):
            print(f"{BOLD}⚠️  HMDA Preview Warning:{RESET} Score is {RISK_COLORS.get(level,'')}{score}/100 ({level}){RESET}.")
            print(f"   A git push or commit with these changes would be {BOLD}blocked{RESET} by the hook.")
            print(f"   Use the MDT What-If Simulator at http://localhost:5173 to test graph fixes beforehand.")
            sys.exit(0)

        if not FORCE:
            print(f"MDT: Commit/Push {BOLD}blocked{RESET} — risk score is {RISK_COLORS.get(level,'')}{score}/100 ({level}){RESET}.")
            print(f"     Fix the architectural issues or bypass with:  MDT_FORCE=1 git push")
            sys.exit(1)

    print(f"MDT: ✓ Approved (HMDA risk = {score}/100 {level})")
    sys.exit(0)


if __name__ == "__main__":
    main()
