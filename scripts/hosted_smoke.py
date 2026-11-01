"""Opt-in hosted-container smoke: prepare, restart the container, then verify.

Run inside a disposable hosted validation container against a test database.
Only the configured public demo repository is read; no GitHub writes occur.
The verify phase deletes the test project. Credentials are never printed.
"""
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._smoke import authenticate, options

base = None
state_path = None
job_timeout = 180
token = None


def request(path, body=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def completed(ident):
    deadline = time.monotonic() + job_timeout + 30
    while time.monotonic() < deadline:
        job = request("/v1/jobs/" + ident)
        if job["status"] in {"succeeded", "partial", "failed", "cancelled"}:
            assert job["status"] in {"succeeded", "partial"}, job.get("error")
            return job
        time.sleep(1)
    raise AssertionError("Job did not terminate within its deadline")


def verify_hosted_boundaries():
    ready = request("/health/ready")
    assert ready["status"] == "ready" and ready["profile"] == "hosted"
    # Published deployments intentionally hide OpenAPI and the legacy fleet API.
    for path in ("/openapi.json", "/registry/context", "/services/graph"):
        try:
            request(path)
        except urllib.error.HTTPError as error:
            assert error.code == 404, "Unexpected hosted route response"
        else:
            raise AssertionError("A disabled research/documentation route was exposed")


def main():
    global base, token, state_path, job_timeout
    args = options(__doc__, hosted=True)
    base, state_path, job_timeout = args.base_url, args.state, args.job_timeout
    verify_hosted_boundaries()
    token = authenticate(args)
    mode = args.mode
    if mode == "prepare":
        if state_path.exists():
            raise SystemExit("State file already exists; select a new --state path to preserve the prior run.")
        project = request("/v1/projects", {"name": "Disposable hosted persistence validation", "repo_url": args.repo_url, "branch": args.branch})
        state = {"project_id": project["id"], "base_url": base, "name": project["name"]}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state))
        try:
            imported = completed(project["job_id"])
            saved = request("/v1/projects/" + project["id"])
            assert saved["ready"]
            revision = saved["snapshot"]["project"]["revision"]
            assert len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)
            submitted = request(f"/v1/projects/{project['id']}/analyses", {"source": "commit", "head_ref": revision})
            analysis = completed(submitted["job_id"])
            assert analysis["result"]["commit_sha"] == revision
            assert analysis["result"]["evidence"]["semantic_used"] is False
            state.update(job_id=submitted["job_id"], snapshot_version=analysis["result"]["snapshot_version"], revision=revision)
            state_path.write_text(json.dumps(state))
            print(json.dumps({"public_import": imported["status"], "services": len(saved["snapshot"]["services"]),
                              "commit_analysis": analysis["status"], "revision": revision,
                              "next": "Restart the validation container, then run this script with verify"}))
        except BaseException:
            request("/v1/projects/" + project["id"], method="DELETE")
            state_path.unlink(missing_ok=True)
            raise
    elif mode == "verify":
        state = json.loads(state_path.read_text())
        if state.get("base_url") != base or not state.get("name", "").startswith("Disposable hosted persistence validation"):
            raise SystemExit("State file does not belong to this smoke test/API; no project was changed.")
        cleanup = False
        try:
            project = request("/v1/projects/" + state["project_id"])
            if project["name"] != state["name"]:
                raise SystemExit("Saved project does not match the disposable smoke state; no project was changed.")
            cleanup = True
            job = request("/v1/jobs/" + state["job_id"])
            assert project["ready"] and job["result"]["commit_sha"] == state["revision"]
            preview = request(f"/v1/analyses/{state['job_id']}/previews", {"edits": [], "snapshot_version": state["snapshot_version"]})
            assert preview["before"] == preview["after"]
            print("Owned project, full result and immutable preview survived the API restart")
        finally:
            if cleanup:
                request("/v1/projects/" + state["project_id"], method="DELETE")
                state_path.unlink(missing_ok=True)
    else:
        raise ValueError("Use prepare or verify")
    if args.revoke_token:
        request("/auth/logout", {}, method="POST")


if __name__ == "__main__":
    raise SystemExit(main())
