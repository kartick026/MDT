"""Replay pinned ten-repository sources against the current application core.

Use a disposable container/copy; the live project store is never opened. Archives
replace only source transport. No repository source/build hooks are executed.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time


async def replay(args):
    from core.registry import RegistryManager
    from domain.architecture import GraphSnapshot, detect_smells, configured_thresholds, DETECTOR_VERSION
    from services.git_analyzer import GitAnalyzer
    from services.impact_engine import ImpactEngine
    from services.public_github_source import PublicGitHubArchive
    from services.repo_onboarding import RepoOnboarder
    from services.remediation_simulator import compute_architecture_health, breakdown_smells
    from services.analysis_evidence import assess_evidence

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    cache = json.loads((args.archives / "archives.json").read_text(encoding="utf-8"))
    lookup = {row["repo"]: row for row in cache}
    records = []
    for prior in baseline["results"]:
        name, revision = prior["repo"], prior["sha"]
        metadata = lookup[name]
        raw = (args.archives / metadata["archive"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == metadata["sha256"]
        archive = PublicGitHubArchive.from_bytes(raw, revision)

        class ArchiveTransport:
            _headers, _token = {}, ""
            source_evidence = archive.evidence

            async def get_repo_tree(self, owner, repo, ref):
                assert ref == revision and owner + "/" + repo == name
                return sorted(archive.files)

            async def get_file_content(self, owner, repo, path, ref):
                assert ref == revision
                return archive.read(path)

            async def _public_archive(self, owner, repo, ref):
                if ref == revision:
                    return archive
                # Download/read the actual recorded parent; never synthesize its files.
                file = args.archives / (name.replace("/", "__") + "__" + ref + ".tar.gz")
                if file.exists():
                    return PublicGitHubArchive.from_bytes(file.read_bytes(), ref)
                return await PublicGitHubArchive.fetch(owner, repo, ref)

        onboarder = RepoOnboarder()
        onboarder.gh_client = ArchiveTransport()
        started = time.perf_counter()
        record = {"repo": name, "sha": revision, "archive_sha256": metadata["sha256"],
                  "before": {key: prior.get(key) for key in ("nodes", "edges", "architectural_debt", "commit_risk")}}
        with RegistryManager.use_snapshot({"services": [], "dependencies": [], "file_mappings": {}}, "replay-" + name):
            try:
                imported = await onboarder.import_from_repo("https://github.com/" + name, revision)
            except ValueError as error:
                record.update(status="abstained", reason=str(error), nodes=None, edges=None, architectural_debt=None, commit_risk=None)
            else:
                data = RegistryManager.load()
                graph = GraphSnapshot.from_data(data)
                findings = detect_smells(graph, configured_thresholds())
                health = compute_architecture_health(breakdown_smells(findings), graph)
                record.update(status=imported["status"], nodes=len(data["services"]), edges=len(data["dependencies"]),
                              architectural_debt=health["score"], architecture_health=health, findings=findings,
                              graph=data, snapshot_version=graph.version, coverage=imported["coverage"], commit_risk=None)
                if prior.get("base_sha") and not args.imports_only:
                    analyzer = GitAnalyzer()
                    analyzer._gh = ArchiveTransport()
                    changes = await analyzer._analyze_public_archives(*name.split("/"), revision, base_sha=prior["base_sha"])
                    engine = ImpactEngine()
                    effective = [change for change in changes if change.ast_metadata.get("semantic_change") is not False]
                    factors = engine._calculate_deterministic_risk(effective)
                    affected, depth = await engine._get_impacted_services_with_depth(effective)
                    factors.dependency_depth = depth
                    risk = engine._compute_base_risk(factors)
                    confidence, status, evidence = assess_evidence(changes, data)
                    record.update(commit_risk=round(risk, 1), risk_scope="deterministic core; semantic retrieval disabled",
                                  base_sha=prior["base_sha"], extraction=analyzer.last_extraction,
                                  evidence_completeness=confidence, assessment_status=status, confidence_evidence=evidence,
                                  risk_factors=vars(factors), impacted_services=sorted(affected),
                                  changes=[{"path": c.file_path, "semantic_change": c.ast_metadata.get("semantic_change"),
                                            "status": c.extraction_status} for c in changes])
                # Version and findings must be stable without modifying captured input.
                assert graph.version == GraphSnapshot.from_data(data).version
                assert findings == detect_smells(GraphSnapshot.from_data(data), configured_thresholds())
        record["seconds"] = round(time.perf_counter() - started, 3)
        records.append(record)
        print(json.dumps({key: record.get(key) for key in ("repo", "status", "nodes", "edges", "architectural_debt", "commit_risk", "seconds")}), flush=True)
        result = {"date": datetime.now(timezone.utc).date().isoformat(), "detector_version": DETECTOR_VERSION,
                  "method": ("Pinned public archive replay through current importer and detector"
                             + ("; commit analysis not rerun" if args.imports_only else " and deterministic risk core")
                             + "; not a Browser rerun or calibrated accuracy evaluation"),
                  "executed_repository_code": False, "results": records,
                  "source_sha256": {str(path.relative_to(args.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in sorted((args.root / "backend").rglob("*.py"))}}
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--imports-only", action="store_true", help="Replay cached topology imports without fetching parent commits")
    args = parser.parse_args()
    args.root = Path(__file__).resolve().parents[1]
    args.baseline, args.archives, args.output = args.baseline.resolve(), args.archives.resolve(), args.output.resolve()
    with tempfile.TemporaryDirectory(prefix="mdt-evidence-replay-") as directory:
        clean = Path(directory)
        shutil.copytree(args.root / "backend", clean / "backend",
                        ignore=shutil.ignore_patterns(".env", ".env.*", "data", "__pycache__", "*.pyc", "chroma_db"))
        os.environ.update(TESTING="true", ENVIRONMENT="test", RUNTIME_PROFILE="local", OPENAI_API_KEY="",
                          GITHUB_TOKEN="", GITHUB_APP_ID="", GITHUB_APP_PRIVATE_KEY="", DATABASE_URL=str(clean / "store.sqlite3"),
                          NEO4J_URI="bolt://127.0.0.1:1", CHROMA_HOST="127.0.0.1")
        os.chdir(clean)
        sys.path.insert(0, str(clean / "backend"))
        asyncio.run(replay(args))


if __name__ == "__main__":
    main()
