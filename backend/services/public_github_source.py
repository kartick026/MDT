"""Bounded, read-only public GitHub fallback when anonymous REST quota is spent.

Archives are pinned to a commit, kept within one client, never extracted to disk,
and never executed. Git fetch reads commit metadata only, without checkout/hooks.
"""
import asyncio
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

import httpx

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_FILES = 20000
MAX_FILE_BYTES = 256 * 1024


class PublicGitHubArchive:
    def __init__(self, files, digests, evidence):
        self.files, self.digests, self.evidence = files, digests, evidence

    @classmethod
    async def fetch(cls, owner, repo, revision):
        if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in (owner, repo)) or not re.fullmatch(r"[a-fA-F0-9]{40}", revision):
            raise ValueError("Public archives require a GitHub repository and exact commit SHA")
        url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/{revision}"
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            async with client.stream("GET", url, headers={"User-Agent": "MDT-public-source"}) as response:
                if response.status_code != 200:
                    raise ValueError(f"Public source archive unavailable (HTTP {response.status_code})")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_ARCHIVE_BYTES:
                        raise ValueError("Public source archive exceeds the 64 MiB download limit")
        return await asyncio.to_thread(cls.from_bytes, bytes(raw), revision)

    @classmethod
    def from_bytes(cls, raw, revision):
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ValueError("Public source archive exceeds the download limit")
        files, digests, total = {}, {}, 0
        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    path = member.name.partition("/")[2]
                    if not path or path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
                        raise ValueError("Unsafe public archive source path")
                    if path in files:
                        raise ValueError("Duplicate public archive source path")
                    total += member.size
                    if member.size < 0 or total > MAX_EXPANDED_BYTES or len(files) >= MAX_ARCHIVE_FILES:
                        raise ValueError("Public source archive exceeds expanded source limits")
                    if member.size > MAX_FILE_BYTES:
                        # Equality can be proved without admitting a large blob
                        # to the source parser or keeping its contents in memory.
                        digest = hashlib.sha256()
                        stream = archive.extractfile(member)
                        for chunk in iter(lambda: stream.read(65536), b""):
                            digest.update(chunk)
                        files[path], digests[path] = None, digest.hexdigest()
                        continue
                    source = archive.extractfile(member).read(MAX_FILE_BYTES + 1)
                    files[path], digests[path] = source, hashlib.sha256(source).hexdigest()
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise ValueError("Public source archive could not be decoded") from exc
        return cls(files, digests, {"transport": "public_github_archive", "revision": revision,
            "archive_sha256": hashlib.sha256(raw).hexdigest(), "download_bytes": len(raw), "expanded_bytes": total,
            "tree_files": len(files), "executed_source": False})

    def read(self, path):
        if path not in self.files:
            raise ValueError("Source path absent from the pinned archive")
        source = self.files[path]
        if source is None:
            raise ValueError("Source exceeds the 256 KiB per-file limit")
        try:
            return source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Source is binary or non-UTF-8") from exc


def public_commit_metadata(owner, repo, revision):
    """Fetch only two commit objects; no checkout, user Git config or repo code."""
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in (owner, repo)) or not re.fullmatch(r"[a-fA-F0-9]{40}", revision):
        raise ValueError("Commit metadata requires an exact public GitHub revision")
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "GIT_CONFIG_COUNT": "0"}
    with tempfile.TemporaryDirectory(prefix="mdt-public-metadata-") as directory:
        def run(*arguments, timeout=35):
            try:
                return subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, *arguments],
                    cwd=directory, env=env, capture_output=True, text=True, check=True, timeout=timeout).stdout.strip()
            except (subprocess.SubprocessError, OSError) as exc:
                raise ValueError("Public commit metadata unavailable within the bounded fetch deadline") from exc
        run("init", "--bare", "--quiet")
        # GitHub supports tree:0. The fetch has no checkout and no source blobs.
        run("fetch", "--quiet", "--depth=2", "--filter=tree:0", "--no-tags",
            f"https://github.com/{owner}/{repo}.git", revision)
        if sum(path.stat().st_size for path in Path(directory).rglob("*") if path.is_file()) > 8 * 1024 * 1024:
            raise ValueError("Public commit metadata exceeded the 8 MiB limit")
        sha, parents, timestamp = run("show", "--no-patch", "--format=%H%n%P%n%ct", "FETCH_HEAD").split("\n")
        if sha.lower() != revision.lower():
            raise ValueError("Public commit metadata did not match requested revision")
        return {"sha": sha, "parents": parents.split(), "timestamp": int(timestamp)}
