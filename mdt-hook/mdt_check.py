#!/usr/bin/env python3
"""Analyze actual staged/working/push snapshots with MDT.

MDT_PROJECT_ID selects an imported project; MDT_API_TOKEN supplies authentication.
The default uses durable /v1 jobs. MDT_API_MODE=legacy explicitly opts into the
old local-only endpoint. Hook failures block by default;
MDT_ON_ERROR=warn explicitly opts into fail-open operation (never reported safe).
MDT_SKIP=1 skips; MDT_FORCE=1 bypasses a risk block, not an extraction failure.
Untracked files are excluded unless --include-untracked is explicitly supplied.
"""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

BASE_URL = os.environ.get("MDT_API_URL", "http://localhost:8000").rstrip("/")
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_FILES = 100
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
ZERO_SHA = "0" * 40


def _git(args, *, check=True):
    result = subprocess.run(["git", "-c", "core.quotepath=false", *args], capture_output=True, timeout=15)
    if check and result.returncode:
        raise ValueError("Git could not resolve the requested repository state: " + result.stderr.decode("utf-8", "replace")[:300])
    return result


def _run_git(args):
    return _git(args).stdout.decode("utf-8", "strict").strip()


def _head():
    result = _git(["rev-parse", "--verify", "HEAD^{commit}"], check=False)
    return result.stdout.decode().strip() if result.returncode == 0 else EMPTY_TREE


def _repo_url():
    url = os.environ.get("MDT_REPO_URL") or _run_git(["remote", "get-url", "origin"])
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:"):]
    if not url:
        raise ValueError("Set origin or MDT_REPO_URL; a different repository is never substituted.")
    return url


def _read_blob(ref, path, *, absent=False):
    if absent:
        return ""
    spec = f"{ref}:{path}" if ref else f":{path}"
    size = int(_run_git(["cat-file", "-s", spec]))
    if size > MAX_FILE_BYTES:
        raise ValueError(f"{path} exceeds the 256 KiB source limit.")
    content = _git(["show", spec]).stdout
    if b"\x00" in content:
        raise ValueError(f"{path} is binary and cannot be safely analyzed by this hook.")
    return content.decode("utf-8", "strict")


def _read_working(path):
    root = Path(_run_git(["rev-parse", "--show-toplevel"])).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Working-tree source points outside the repository.")
    if not target.is_file():
        return ""
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{path} exceeds the 256 KiB source limit.")
    data = target.read_bytes()
    if b"\x00" in data:
        raise ValueError(f"{path} is binary and cannot be safely analyzed by this hook.")
    return data.decode("utf-8", "strict")


def _build_payload(mode, *, base=None, head=None, paths=None, include_untracked=False):
    head = head or _head()
    base = base or head
    args = ["diff", "--name-status", "-z", "--find-renames", "--no-ext-diff"]
    if mode == "staged":
        args += ["--cached", base]
    elif mode == "working":
        args += [base]
    else:
        args += [base, head]
    args += ["--", *(paths or [])]
    records = _git(args).stdout.decode("utf-8", "strict").split("\x00")
    entries, index = [], 0
    while index < len(records) and records[index]:
        status, path = records[index], records[index + 1]
        index += 2
        previous = None
        if status[0] in {"R", "C"}:
            previous, path = path, records[index]
            index += 1
        entries.append((status[0], path, previous))
    if include_untracked and mode == "working":
        untracked = _git(["ls-files", "--others", "--exclude-standard", "-z", "--", *(paths or [])]).stdout.decode("utf-8", "strict")
        entries.extend(("A", path, None) for path in untracked.split("\x00") if path)
    if len(entries) > MAX_FILES:
        raise ValueError(f"The change contains {len(entries)} files; the alpha limit is {MAX_FILES}.")
    changes, size = [], 0
    for status, path, previous in entries:
        kind = {"A": "added", "D": "deleted", "R": "renamed", "C": "copied"}.get(status, "modified")
        old = _read_blob(base, previous or path, absent=kind == "added" or base == EMPTY_TREE)
        if kind == "deleted":
            new = ""
        elif mode == "working":
            new = _read_working(path)
        else:
            new = _read_blob("" if mode == "staged" else head, path)
        size += len(old.encode()) + len(new.encode())
        if size > MAX_TOTAL_BYTES:
            raise ValueError("Source snapshots exceed the 2 MiB total limit.")
        changes.append({"file_path": path, "previous_path": previous, "change_type": kind,
                        "old_content": old, "new_content": new})
    identity = hashlib.sha256(json.dumps(changes, sort_keys=True).encode()).hexdigest()
    return {"repo_url": _repo_url(), "commit_sha": head, "base_sha": base,
            "input_mode": mode, "comparison_mode": "direct", "local_changes": changes,
            "changed_files": [change["file_path"] for change in changes],
            "snapshot_digest": identity}


def _pre_push_payloads(stream):
    """Git supplies one local-ref/local-SHA/remote-ref/remote-SHA line per updated ref."""
    for line in stream:
        parts = line.split()
        if len(parts) != 4:
            raise ValueError("Invalid pre-push input; expected Git's four ref fields.")
        local_ref, local_sha, remote_ref, remote_sha = parts
        if local_sha == ZERO_SHA:
            continue  # Branch deletion has no new code to analyze.
        if remote_sha == ZERO_SHA:
            default_ref = os.environ.get("MDT_BASE_REF", "refs/remotes/origin/HEAD")
            result = _git(["merge-base", local_sha, default_ref], check=False)
            remote_sha = result.stdout.decode().strip() if result.returncode == 0 else EMPTY_TREE
        yield _build_payload("push", base=remote_sha, head=local_sha)


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError("MDT redirected the request. Set MDT_API_URL to the final API URL; credentials were not forwarded.")


def _server_url(value):
    url = urllib.parse.urlsplit(value)
    loopback = url.hostname in {"localhost", "127.0.0.1", "::1"}
    if url.scheme != "https" and not (url.scheme == "http" and loopback):
        raise ValueError("MDT_API_URL must use HTTPS, or HTTP on localhost for development.")
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("MDT_API_URL must not contain credentials, a query, or a fragment.")
    return value.rstrip("/")


def _repository_key(value):
    value = value.strip().replace("git@github.com:", "https://github.com/", 1)
    url = urllib.parse.urlsplit(value)
    if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password or url.query or url.fragment:
        raise ValueError("The hook requires a github.com origin or an explicit HTTPS MDT_REPO_URL.")
    parts = url.path.strip("/").removesuffix(".git").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("The repository URL must identify a GitHub owner/repository.")
    return "/".join(parts).lower()


def _request(path, *, method="GET", payload=None, timeout=20, idempotency_key=None):
    headers = {"Accept": "application/json", "Authorization": f"Bearer {os.environ.get('MDT_API_TOKEN', '').strip()}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(f"{_server_url(BASE_URL)}{path}", data, headers, method=method)
    try:
        with urllib.request.build_opener(_NoRedirects()).open(request, timeout=timeout) as response:
            data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError("MDT returned a response larger than the 4 MiB client limit.")
            try:
                result = json.loads(data)
            except (ValueError, UnicodeError) as exc:
                raise ValueError("MDT returned invalid JSON. Check MDT_API_URL points to the API, not the website.") from exc
            if not isinstance(result, dict):
                raise ValueError("MDT returned an unexpected response format.")
            return result
    except urllib.error.HTTPError as exc:
        # Error bodies may contain echoed source or tokens. Only expose known guidance.
        guidance = {401: "Session expired. Copy a new MDT token from Account.",
                    403: "An analyst account is required for analysis.",
                    404: "Check MDT_API_URL and MDT_PROJECT_ID; the project/job must belong to this account.",
                    409: "The project changed or is still importing. Refresh it and retry.",
                    413: "Source upload is too large. Analyze a smaller change.",
                    422: "The API rejected the source input. Check client/server versions and source limits.",
                    429: "The account or provider quota was reached. Retry after its reset."}
        raise ValueError(f"MDT API returned HTTP {exc.code}: {guidance.get(exc.code, 'The server could not complete the request; inspect its logs.')} ") from exc


def _call_api(payload):
    if not os.environ.get("MDT_API_TOKEN", "").strip():
        raise ValueError("Set MDT_API_TOKEN to a short-lived MDT session token from Account.")
    _server_url(BASE_URL)
    mode = os.environ.get("MDT_API_MODE", "v1")
    if mode == "legacy":
        return _request("/analysis/analyze", method="POST", payload=payload, timeout=90)
    if mode != "v1":
        raise ValueError("MDT_API_MODE must be v1 or the explicit local compatibility option legacy.")
    project_id = os.environ.get("MDT_PROJECT_ID", "").strip()
    if not project_id:
        raise ValueError("Set MDT_PROJECT_ID to an imported project ID from the web project URL (?project=...).")
    project = _request(f"/v1/projects/{urllib.parse.quote(project_id, safe='')}")
    if _repository_key(project.get("repo_url", "")) != _repository_key(payload["repo_url"]):
        raise ValueError("MDT_PROJECT_ID belongs to a different repository. No source was uploaded.")
    if not project.get("ready") or not project.get("snapshot_version"):
        raise ValueError("Wait for this project's architecture import to finish before running the hook.")
    body = {"source": "patch", "base_ref": payload["base_sha"], "head_ref": payload["commit_sha"],
            "comparison_mode": "direct", "local_changes": payload["local_changes"],
            "changed_files": payload["changed_files"], "snapshot_version": project["snapshot_version"]}
    wait_seconds = float(os.environ.get("MDT_WAIT_SECONDS", "120"))
    if not 5 <= wait_seconds <= 300:
        raise ValueError("MDT_WAIT_SECONDS must be between 5 and 300 seconds.")
    deadline = time.monotonic() + wait_seconds
    submitted = _request(f"/v1/projects/{urllib.parse.quote(project_id, safe='')}/analyses", method="POST",
                         payload=body, idempotency_key=uuid.uuid4().hex, timeout=min(20, wait_seconds))
    job_id = submitted.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("MDT did not return a job ID; inspect project history before retrying.")
    job_path = f"/v1/jobs/{urllib.parse.quote(job_id, safe='')}"
    completed = False
    print(f"MDT: submitted job {job_id}; waiting up to {wait_seconds:g}s.")
    try:
        while time.monotonic() < deadline:
            job = _request(job_path, timeout=max(0.1, min(20, deadline - time.monotonic())))
            state = job.get("status")
            if state in {"succeeded", "completed", "partial", "failed", "cancelled"}:
                completed = True
                if state not in {"succeeded", "completed"}:
                    raise ValueError(f"Analysis {state}; inspect job {job_id} in project History.")
                result = job.get("result")
                if not isinstance(result, dict):
                    raise ValueError("Completed job has no analysis result.")
                return {**result, "status": "success"}
            if state not in {"queued", "running"}:
                raise ValueError("The server returned an unknown job status.")
            time.sleep(min(1.5, max(0, deadline - time.monotonic())))
        raise ValueError(f"Analysis exceeded {wait_seconds:g}s. Review job {job_id} before retrying.")
    finally:
        if not completed:
            try:
                _request(job_path, method="DELETE", timeout=5)
                print(f"MDT: cancellation requested for job {job_id}.", file=sys.stderr)
            except (ValueError, OSError) as exc:
                print(f"MDT: cancellation could not be confirmed for job {job_id}: {exc}", file=sys.stderr)


def _install_hook(kind, replace=False):
    target = Path(_run_git(["rev-parse", "--git-path", f"hooks/{kind}"]))
    if target.exists() and "# MDT " not in target.read_text(encoding="utf-8", errors="replace") and not replace:
        raise ValueError(f"Existing {kind} hook preserved. Integrate MDT manually or explicitly pass --replace-hook.")
    target.parent.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve().as_posix()
    interpreter = Path(sys.executable).resolve().as_posix()
    target.write_text(f"#!/usr/bin/env sh\n# MDT {kind} hook\nexec {shlex.quote(interpreter)} {shlex.quote(script)} --{kind} \"$@\"\n", encoding="utf-8", newline="\n")
    target.chmod(0o755)
    print(f"MDT hook installed: {target}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", "-s", action="store_true")
    group.add_argument("--working", "-w", action="store_true")
    group.add_argument("--pre-commit", action="store_true")
    group.add_argument("--pre-push", action="store_true")
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument("--dry-run", "-d", action="store_true")
    parser.add_argument("--on-error", choices=["block", "warn"], default=os.environ.get("MDT_ON_ERROR", "block"))
    parser.add_argument("--install-hook", choices=["pre-commit", "pre-push"])
    parser.add_argument("--replace-hook", action="store_true")
    args = parser.parse_args(argv)
    if os.environ.get("MDT_SKIP") == "1":
        print("MDT: explicitly skipped; no analysis performed.")
        return 0
    try:
        if args.install_hook:
            _install_hook(args.install_hook, args.replace_hook)
            return 0
        if args.pre_push:
            payloads = list(_pre_push_payloads(sys.stdin))
        else:
            mode = "staged" if args.staged or args.pre_commit else "working"
            payloads = [_build_payload(mode, paths=args.files, include_untracked=args.include_untracked)]
        for payload in payloads:
            if not payload["local_changes"]:
                print("MDT: no changed files in this ref or selection.")
                continue
            result = _call_api(payload)
            status = result.get("status", "unknown")
            coverage = result.get("extraction", result.get("coverage", {})) or {}
            if status not in {"success", "complete"} or result.get("partial_results") or coverage.get("status") == "partial":
                raise ValueError("Analysis is incomplete; inspect extraction/coverage warnings in the dashboard.")
            level = (result.get("severity") or "UNKNOWN").upper()
            score = result.get("risk_score")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100 or level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ValueError("The API returned an unrecognized analysis result.")
            print(f"MDT: {len(payload['local_changes'])} files; risk {score}/100 ({level}).")
            if result.get("explanation"):
                print(result["explanation"][:500])
            if level in {"HIGH", "CRITICAL"} and not args.dry_run and os.environ.get("MDT_FORCE") != "1":
                print("MDT: blocked by risk policy. Review findings or explicitly set MDT_FORCE=1.")
                return 1
        return 0
    except KeyboardInterrupt:
        print("MDT: interrupted; the change was not approved.", file=sys.stderr)
        return 130
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print(f"MDT: check unavailable: {exc}", file=sys.stderr)
        if args.on_error == "warn":
            print("MDT: proceeding under explicit warn policy; the change was NOT approved.", file=sys.stderr)
            return 0
        return 2


if __name__ == "__main__":
    sys.exit(main())
