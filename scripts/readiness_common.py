"""Local evidence identities. No network, credentials, deployment or publication."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("backend", "frontend", "extensions", "packages", "tests", "scripts",
                ".github", "evaluation", "readiness-policy.json", "release-config.example.json",
                "requirements-test.txt", "pytest.ini", "docker-compose.yml")
GENERATED = {"node_modules", "dist", "build", "__pycache__", "data", ".pytest_cache"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identity(root=ROOT):
    """Bind evidence to relevant tracked AND untracked source, not just HEAD.

    Byte-sensitive by design: create fresh evidence in each release build.
    Generated archives/reports are separately hashed, avoiding self-hash cycles.
    """
    listing = subprocess.run(["git", "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard", "--", *SOURCE_ROOTS],
                             cwd=root, check=True, capture_output=True).stdout
    names = sorted(set(listing.decode("utf-8").split("\0")) - {""})
    digest = hashlib.sha256()
    count = 0
    for name in names:
        path = Path(root) / name
        if GENERATED.intersection(Path(name).parts) or path.suffix in {".zip", ".vsix", ".png", ".jpg"}:
            continue
        if path.is_symlink():
            raise ValueError("Source identity does not accept symlinks: " + name)
        if not path.exists():
            continue  # A tracked deletion is represented by its absence.
        digest.update(name.encode("utf-8") + b"\0" + bytes.fromhex(digest_file(path)))
        count += 1
    if not count:
        raise ValueError("No release source files found")
    return {"sha256": digest.hexdigest(), "files": count}


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evidence(kind, **fields):
    return {"schema_version": 1, "kind": kind, "created_at": utc_now(),
            "source": source_identity(), **fields}
