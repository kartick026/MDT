"""Hook contract checks, including actual loopback HTTP and redirect handling."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def hook(monkeypatch):
    spec = importlib.util.spec_from_file_location("hook_v1_test", Path(__file__).parents[1] / "mdt-hook/mdt_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("MDT_API_TOKEN", "test-session-token")
    monkeypatch.setenv("MDT_PROJECT_ID", "project-1")
    monkeypatch.delenv("MDT_API_MODE", raising=False)
    monkeypatch.delenv("MDT_WAIT_SECONDS", raising=False)
    return module


@pytest.fixture
def payload():
    return {"repo_url": "git@github.com:example/service.git", "base_sha": "a" * 40, "commit_sha": "b" * 40,
            "local_changes": [{"file_path": "app.py", "old_content": "before", "new_content": "after", "change_type": "modified"}],
            "changed_files": ["app.py"]}


def project():
    return {"repo_url": "https://github.com/example/service", "ready": True, "snapshot_version": "v1"}


@pytest.fixture
def server():
    calls = []
    responses = {}

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append({"method": self.command, "path": self.path, "body": json.loads(raw) if raw else None,
                          "authorization": self.headers.get("Authorization"), "key": self.headers.get("Idempotency-Key")})
            status, body = responses.get((self.command, self.path), (404, {"detail": "missing"}))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if status == 302:
                self.send_header("Location", "/credential-leak")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        do_GET = handle_request
        do_POST = handle_request
        do_DELETE = handle_request

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", responses, calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


def test_hook_uses_project_owned_async_job_with_real_http(hook, payload, server):
    hook.BASE_URL, responses, calls = server
    responses["GET", "/v1/projects/project-1"] = (200, project())
    responses["POST", "/v1/projects/project-1/analyses"] = (202, {"job_id": "job-1"})
    responses["GET", "/v1/jobs/job-1"] = (200, {"status": "succeeded", "result": {"risk_score": 25, "severity": "LOW"}})
    result = hook._call_api(payload)
    assert result == {"risk_score": 25, "severity": "LOW", "status": "success"}
    assert len(calls) == 3
    assert all(call["authorization"] == "Bearer test-session-token" for call in calls)
    submitted = calls[1]
    assert submitted["body"] == {"source": "patch", "base_ref": "a" * 40, "head_ref": "b" * 40,
                                 "comparison_mode": "direct", "snapshot_version": "v1",
                                 "local_changes": payload["local_changes"], "changed_files": ["app.py"]}
    assert len(submitted["key"]) == 32


def test_mismatched_repository_never_uploads_source(hook, payload):
    with patch.object(hook, "_request", return_value={**project(), "repo_url": "https://github.com/another/repository"}) as request:
        with pytest.raises(ValueError, match="different repository"):
            hook._call_api(payload)
    assert request.call_count == 1


def test_not_ready_project_blocks_before_submission(hook, payload):
    with patch.object(hook, "_request", return_value={**project(), "ready": False}) as request:
        with pytest.raises(ValueError, match="import"):
            hook._call_api(payload)
    assert request.call_count == 1


def test_timeout_cancels_queued_job(hook, payload, monkeypatch):
    monkeypatch.setenv("MDT_WAIT_SECONDS", "5")
    with patch.object(hook, "_request", side_effect=[project(), {"job_id": "job-1"}, {"status": "cancelled"}]) as request:
        with patch.object(hook.time, "monotonic", side_effect=[10, 16]):
            with pytest.raises(ValueError, match="exceeded"):
                hook._call_api(payload)
    assert request.call_args.kwargs == {"method": "DELETE", "timeout": 5}


def test_interruption_cancels_job(hook, payload):
    with patch.object(hook, "_request", side_effect=[project(), {"job_id": "job-1"}, KeyboardInterrupt(), {}]) as request:
        with pytest.raises(KeyboardInterrupt):
            hook._call_api(payload)
    assert request.call_args.kwargs["method"] == "DELETE"


def test_redirect_never_forwards_token(hook, payload, server):
    hook.BASE_URL, responses, calls = server
    responses["GET", "/v1/projects/project-1"] = (302, {})
    with pytest.raises(ValueError, match="redirected"):
        hook._call_api(payload)
    assert len(calls) == 1


def test_auth_error_gives_action_without_echoing_error_body(hook, payload, server):
    hook.BASE_URL, responses, _ = server
    responses["GET", "/v1/projects/project-1"] = (401, {"detail": "sensitive-echo"})
    with pytest.raises(ValueError, match="Copy a new MDT token") as error:
        hook._call_api(payload)
    assert "sensitive-echo" not in str(error.value)


@pytest.mark.parametrize("url", ["http://remote.example", "https://user:pass@example.com", "https://example.com/?token=secret", "https://example.com/#secret"])
def test_unsafe_server_urls_block(hook, url):
    with pytest.raises(ValueError):
        hook._server_url(url)


def test_configuration_required_without_silent_legacy_fallback(hook, payload, monkeypatch):
    monkeypatch.delenv("MDT_PROJECT_ID")
    with pytest.raises(ValueError, match="MDT_PROJECT_ID"):
        hook._call_api(payload)
    monkeypatch.delenv("MDT_API_TOKEN")
    with pytest.raises(ValueError, match="MDT_API_TOKEN"):
        hook._call_api(payload)


def test_legacy_is_explicit_opt_in(hook, payload, monkeypatch):
    monkeypatch.setenv("MDT_API_MODE", "legacy")
    monkeypatch.delenv("MDT_PROJECT_ID")
    with patch.object(hook, "_request", return_value={}) as request:
        hook._call_api(payload)
    assert request.call_args.args == ("/analysis/analyze",)


def test_partial_result_never_approves_change(hook, payload):
    with patch.object(hook, "_build_payload", return_value=payload), patch.object(hook, "_call_api", return_value={
        "status": "success", "risk_score": 0, "severity": "LOW", "partial_results": True
    }):
        assert hook.main(["--staged"]) == 2
