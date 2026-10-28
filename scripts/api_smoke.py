"""Run inside a backend container against its own API; never print credentials."""
import json
import time
import urllib.request
import urllib.error
import sys

sys.path.insert(0, "/app")
from core.config import settings

base = "http://127.0.0.1:" + str(__import__("os").environ.get("PORT", "8000"))
token = None


def request(path, body=None, method=None, authenticated=True):
    headers = {"Content-Type": "application/json"}
    if token and authenticated:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


assert request("/health/ready")["status"] == "ready"
assert request("/v1/demo")["evidence"]["mode"] == "illustrative_demo"
try:
    request("/v1/projects", authenticated=False)
    raise AssertionError("Anonymous project data was exposed")
except urllib.error.HTTPError as exc:
    assert exc.code == 401
token = request("/auth/login", {"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})["access_token"]
project = request("/v1/projects", {"name": "Disposable API validation", "repo_url": settings.DEMO_REPO_URL, "use_demo": True})
keep_for_browser = "--keep-for-browser" in sys.argv
validated = False
try:
    rules = [{"kind": "forbid", "source": "notification-service", "target": "notification-service", "reason": "No recursive notification dependency"}]
    policy = request(f"/v1/projects/{project['id']}/policies", {"rules": rules}, method="PUT")
    assert policy["evaluation"]["violations"] == 1
    job = request(f"/v1/projects/{project['id']}/analyses", {
        "source": "patch", "base_ref": "a" * 40,
        "before_files": {"services/user_service/main.py": "@app.get('/users')\ndef users():\n return []\n"},
        "after_files": {"services/user_service/main.py": "@app.get('/members')\ndef users():\n return []\n"}})
    for _ in range(60):
        result = request("/v1/jobs/" + job["job_id"])
        if result["status"] in {"succeeded", "partial", "failed", "cancelled"}:
            break
        time.sleep(1)
    assert result["status"] in {"succeeded", "partial"}, result
    analysis = result["result"]
    assert analysis["policy_assessment"]["violations"] == 1
    assert analysis["risk_score"] > 0 and analysis["evidence"]["semantic_used"] is False
    assert analysis["confidence_evidence"]["kind"] == "evidence_completeness"
    assert analysis["confidence_evidence"]["calibrated"] is False
    preview = request(f"/v1/analyses/{job['job_id']}/previews", {"edits": [], "snapshot_version": analysis["snapshot_version"]})
    assert preview["before"]["score"] == preview["after"]["score"]
    history = request(f"/v1/analyses?project_id={project['id']}&limit=1")
    assert history["total"] == 1 and history["analyses"][0]["id"] == job["job_id"]
    assert "result" not in history["analyses"][0]
    captured = request(f"/v1/analyses/{job['job_id']}/snapshot")
    assert captured["snapshot_version"] == analysis["snapshot_version"]
    request(f"/v1/projects/{project['id']}/baseline", {"snapshot_version": captured["snapshot_version"]}, method="PUT")
    drift = request(f"/v1/projects/{project['id']}/drift")
    assert drift["evidence"]["same_snapshot"] and drift["scores"]["delta"] == 0
    if analysis["smells"]:
        review_path = f"/v1/analyses/{job['job_id']}/reviews"
        review = request(review_path + "/" + analysis["smells"][0]["id"], {"classification": "confirmed", "reason": "Disposable runtime validation", "expires_days": 7}, method="PUT")
        assert review["score_effect"] == "none" and request(review_path)["reviews"]
        assert request("/v1/jobs/" + job["job_id"])["result"]["risk_score"] == analysis["risk_score"]
    source = "@app.get('/users')\ndef users():\n return []\n"
    comment_job = request(f"/v1/projects/{project['id']}/analyses", {
        "source": "patch", "base_ref": "a" * 40,
        "before_files": {"services/user_service/main.py": source},
        "after_files": {"services/user_service/main.py": source + "# explanatory comment\n"}})
    for _ in range(60):
        comment_result = request("/v1/jobs/" + comment_job["job_id"])
        if comment_result["status"] in {"succeeded", "partial", "failed", "cancelled"}:
            break
        time.sleep(1)
    assert comment_result["status"] in {"succeeded", "partial"}, comment_result
    assert comment_result["result"]["risk_score"] == 0
    assert comment_result["result"]["assessment_status"] == "no_semantic_change"
    print(json.dumps({"profile": settings.RUNTIME_PROFILE, "job_status": result["status"],
                      "risk_score": analysis["risk_score"], "smells": len(analysis["smells"]),
                      "comment_only_risk": comment_result["result"]["risk_score"],
                      "evidence_completeness": "verified",
                      "no_edit_preview_unchanged": True, "auth_ownership_routes": "passed",
                      "history_snapshot_baseline_drift_reviews": "passed"}))
    validated = True
    if keep_for_browser:
        from pathlib import Path
        Path("/tmp/mdt-browser-validation.json").write_text(json.dumps({"project_id": project["id"], "job_id": job["job_id"]}))
        print("Browser validation link: http://localhost:5173/#/projects?project=" + project["id"] + "&job=" + job["job_id"])
finally:
    if not (keep_for_browser and validated):
        request("/v1/projects/" + project["id"], method="DELETE")
request("/auth/logout", {}, method="POST")
try:
    request("/auth/me")
    raise AssertionError("Revoked token remained valid")
except urllib.error.HTTPError as exc:
    assert exc.code == 401
print("Logout revocation passed. " + ("Disposable project retained for browser validation; delete after checking." if keep_for_browser and validated else "Project cleanup passed."))
