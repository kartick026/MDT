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

sys.path.insert(0, "/app")
from core.config import settings

assert settings.RUNTIME_PROFILE == "hosted"
base = "http://127.0.0.1:" + os.getenv("PORT", "8000")
state_path = Path("/tmp/mdt-hosted-smoke.json")
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
    deadline = time.monotonic() + settings.JOB_TIMEOUT_SECONDS + 30
    while time.monotonic() < deadline:
        job = request("/v1/jobs/" + ident)
        if job["status"] in {"succeeded", "partial", "failed", "cancelled"}:
            assert job["status"] in {"succeeded", "partial"}, job.get("error")
            return job
        time.sleep(1)
    raise AssertionError("Job did not terminate within its deadline")


assert request("/health/ready")["status"] == "ready"
token = request("/auth/login", {"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})["access_token"]
mode = sys.argv[1] if len(sys.argv) > 1 else "prepare"
if mode == "prepare":
    paths = request("/openapi.json")["paths"]
    assert all(p.startswith(("/v1/", "/health", "/auth/")) or p == "/" for p in paths), sorted(paths)
    project = request("/v1/projects", {"name": "Disposable hosted persistence validation", "repo_url": settings.DEMO_REPO_URL, "branch": settings.DEMO_REPO_BRANCH})
    state = {"project_id": project["id"]}
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
    try:
        project = request("/v1/projects/" + state["project_id"])
        job = request("/v1/jobs/" + state["job_id"])
        assert project["ready"] and job["result"]["commit_sha"] == state["revision"]
        preview = request(f"/v1/analyses/{state['job_id']}/previews", {"edits": [], "snapshot_version": state["snapshot_version"]})
        assert preview["before"] == preview["after"]
        print("Owned project, full result and immutable preview survived the API restart")
    finally:
        request("/v1/projects/" + state["project_id"], method="DELETE")
        state_path.unlink(missing_ok=True)
else:
    raise ValueError("Use prepare or verify")
request("/auth/logout", {}, method="POST")
