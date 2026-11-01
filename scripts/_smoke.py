"""Explicit opt-in HTTP smoke-test configuration, without default credentials."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import urllib.request
from urllib.parse import urlsplit


def options(description, hosted=False):
    parser = argparse.ArgumentParser(description=description)
    if hosted:
        parser.add_argument("mode", choices=("prepare", "verify"))
    parser.add_argument("--base-url", default="http://127.0.0.1:" + os.getenv("PORT", "8000"))
    parser.add_argument("--repo-url", default="https://github.com/kartick026/MDT")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--job-timeout", type=float, default=180)
    parser.add_argument("--allow-write", action="store_true", help="Explicitly create/delete only disposable test projects on this API")
    parser.add_argument("--password-login", action="store_true", help="Disposable development deployments only: use MDT_SMOKE_USERNAME and MDT_SMOKE_PASSWORD")
    parser.add_argument("--keep-for-browser", action="store_true")
    parser.add_argument("--revoke-token", action="store_true", help="Also test logout by revoking the supplied test session")
    parser.add_argument("--state", type=Path, default=Path(tempfile.gettempdir()) / ("mdt-hosted-smoke.json" if hosted else "mdt-browser-validation.json"))
    args = parser.parse_args()
    parts = urlsplit(args.base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        parser.error("--base-url must be an HTTP(S) origin without credentials, query or fragment")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use HTTPS for a remote API")
    if hosted and not args.allow_write:
        parser.error("Hosted prepare/verify changes disposable data and requires --allow-write")
    if args.allow_write and not (os.getenv("MDT_SMOKE_TOKEN") or args.password_login):
        parser.error("Set MDT_SMOKE_TOKEN to a disposable Google OAuth test session, or explicitly use --password-login on a test-only deployment")
    if args.password_login and not (os.getenv("MDT_SMOKE_USERNAME") and os.getenv("MDT_SMOKE_PASSWORD")):
        parser.error("--password-login requires explicit MDT_SMOKE_USERNAME and MDT_SMOKE_PASSWORD")
    args.base_url = args.base_url.rstrip("/")
    args.state = args.state.resolve()
    return args


def authenticate(args):
    if not args.password_login:
        return os.getenv("MDT_SMOKE_TOKEN")
    body = json.dumps({"username": os.environ["MDT_SMOKE_USERNAME"], "password": os.environ["MDT_SMOKE_PASSWORD"]}).encode()
    request = urllib.request.Request(args.base_url + "/auth/login", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())["access_token"]
