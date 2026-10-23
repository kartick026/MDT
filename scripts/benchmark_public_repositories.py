"""Opt-in public-source benchmark. Never runs downloaded code or changes the live store.

Run in the backend image with this script read-only and a separate output mount.
Public archives are pinned to the resolved HEAD SHA and cached in the output directory.
Archive-backed reads replace only the GitHub transport; onboarding, parsing, job
evaluation and scoring use the application implementations unchanged.
Controlled edits are experiments on real source, not upstream commits or incidents.
"""
import argparse
import ast
import asyncio
import copy
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
import platform
from pathlib import Path
import re
import resource
import subprocess
import sys
import tarfile
import time
import urllib.request
from unittest.mock import patch

os.environ.update(OPENAI_API_KEY="", GITHUB_TOKEN="", GITHUB_APP_ID="", GITHUB_APP_PRIVATE_KEY="",
                  RUNTIME_PROFILE="local", ENVIRONMENT="development", TESTING="true")
sys.path.insert(0, "/app")
logging.basicConfig(level=logging.ERROR)

REPOSITORIES = ["GoogleCloudPlatform/microservices-demo", "fastapi/full-stack-fastapi-template",
                "expressjs/express", "fastapi/fastapi"]
ONLINE_BOUTIQUE = {"frontend", "cartservice", "productcatalogservice", "currencyservice", "paymentservice",
                   "shippingservice", "emailservice", "checkoutservice", "recommendationservice", "adservice", "loadgenerator"}


def fetch_repository(repo, output, ref="HEAD"):
    directory = output / (repo.replace("/", "__") + ("__" + ref[:12] if ref != "HEAD" else ""))
    directory.mkdir(exist_ok=True)
    metadata_file, archive_file = directory / "provenance.json", directory / "source.tar.gz"
    if metadata_file.exists() and archive_file.exists():
        metadata = json.loads(metadata_file.read_text())
        raw = archive_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata["archive_sha256"]:
            raise ValueError("Cached public archive digest mismatch")
    else:
        url = "https://github.com/" + repo
        resolved = ([ref] if re.fullmatch("[a-f0-9]{40}", ref) else
                    subprocess.run(["git", "ls-remote", url, ref], capture_output=True, text=True,
                                   timeout=45, check=True).stdout.split())
        sha = resolved[0]
        if not re.fullmatch("[a-f0-9]{40}", sha):
            raise ValueError("HEAD did not resolve to an exact commit")
        archive_url = f"https://codeload.github.com/{repo}/tar.gz/{sha}"
        request = urllib.request.Request(archive_url, headers={"User-Agent": "MDT-academic-readonly-benchmark"})
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("Archive exceeds the benchmark download bound")
        metadata = {"repo": repo, "sha": sha, "archive_url": archive_url,
                    "archive_sha256": hashlib.sha256(raw).hexdigest(), "download_bytes": len(raw)}
        archive_file.write_bytes(raw)
        metadata_file.write_text(json.dumps(metadata, indent=2))
    contents, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            path = member.name.partition("/")[2]
            if not path or ".." in path.split("/"):
                continue
            total += member.size
            if total > 256 * 1024 * 1024 or len(contents) >= 20000:
                raise ValueError("Expanded archive exceeds benchmark bounds")
            # Preserve oversized-file membership without reading it as valid source.
            contents[path] = None if member.size > 256 * 1024 else archive.extractfile(member).read()
    metadata["tree_files"] = len(contents)
    print(json.dumps({"downloaded": repo, "sha": metadata["sha"], "files": len(contents)}), flush=True)
    return metadata, contents


class ArchiveTransport:
    def __init__(self, contents):
        self.contents, self._headers, self._token = contents, {}, ""

    async def get_repo_tree(self, owner, repo, revision):
        return sorted(self.contents)

    async def get_file_content(self, owner, repo, path, revision):
        if path not in self.contents:
            return ""
        raw = self.contents[path]
        if raw is None:
            raise ValueError("Source exceeds the 256 KiB per-file limit")
        return raw.decode("utf-8")


def source(contents, path):
    return contents[path].decode("utf-8")


def experiment_cases(repo, contents):
    cases = []
    if repo == "fastapi/full-stack-fastapi-template":
        path = "backend/app/api/routes/items.py"
        code = source(contents, path)
        cases += [("identical_snapshot", {path: code}, {path: code}, False, "No source changes"),
                  ("python_comment_only", {path: code}, {path: code + "\n# MDT comment-only control.\n"}, False,
                   "Only a comment; identical Python AST and HTTP contracts")]
        changed, count = re.subn(r'(@(?:router|app)\.(?:get|post|put|patch|delete)\(\s*)([\"\x27])([^\"\x27]*)([\"\x27])',
                                 lambda m: m[1] + m[2] + "/mdt-renamed-route" + m[4], code, count=1)
        if count != 1:
            raise ValueError("Cannot find a literal template route for the independent control")
        cases.append(("python_route_renamed", {path: code}, {path: changed}, True, "First literal router path renamed"))
        cases.append(("python_route_file_deleted", {path: code}, {}, True, "Entire real route module removed"))
        model_path = "backend/app/models.py"
        models = source(contents, model_path)
        changed_models, count = re.subn(r'(class ItemBase\([^\n]+\):\s*\n\s*title:\s*)str\b', r'\1int', models, count=1)
        if count == 1:
            cases.append(("cross_file_model_type_changed", {model_path: models}, {model_path: changed_models}, True,
                          "ItemBase.title changes str to int; route request/response models inherit it across files"))
            cases.append(("cross_file_model_type_changed_with_context", {model_path: models, path: code},
                          {model_path: changed_models, path: code}, True,
                          "Same type change with the unchanged real route module supplied as bounded context"))
        for label, field in (("optional", "    mdt_optional_note: str | None = None\n"),
                             ("required", "    mdt_required_note: str\n")):
            edited, count = re.subn(r'(class ItemBase\([^\n]+\):\n)', lambda m: m[1] + field, models, count=1)
            if count != 1:
                raise ValueError("Cannot identify ItemBase for the independent compatibility controls")
            cases.append(("cross_file_" + label + "_field_added", {model_path: models, path: code},
                          {model_path: edited, path: code}, True,
                          "Adds a " + label + " inherited ItemBase field; unchanged importing route supplied as context"))
    elif repo == "expressjs/express":
        path = "examples/hello-world/index.js"
        code = source(contents, path)
        cases.append(("javascript_comment_only", {path: code}, {path: code + "\n// MDT comment-only control.\n"}, False,
                      "Only a comment; literal public HTTP routes unchanged"))
        changed, count = re.subn(r'(app\.get\(\s*)([\"\x27])/([\"\x27])', lambda m: m[1] + m[2] + "/mdt-renamed-route" + m[3], code, count=1)
        if count != 1:
            raise ValueError("Cannot find the Express example route")
        cases.append(("javascript_route_renamed", {path: code}, {path: changed}, True, "GET / renamed in the real example"))
        cases.append(("javascript_route_file_deleted", {path: code}, {}, True, "Entire real example module removed"))
    elif repo == "fastapi/fastapi":
        candidates = [(path, raw) for path, raw in contents.items() if raw and path.startswith("fastapi/") and path.endswith(".py")]
        path, raw = max(candidates, key=lambda item: len(item[1]))
        code = raw.decode("utf-8")
        cases.append(("large_python_comment_only", {path: code}, {path: code + "\n# MDT comment-only control.\n"}, False,
                      "Largest bounded FastAPI implementation module; comment only"))
        small = sorted([(path, raw) for path, raw in contents.items() if raw and path.endswith(".py") and 100 < len(raw) < 12000],
                       key=lambda item: (len(item[1]), item[0]))[:100]
        before = {path: raw.decode("utf-8") for path, raw in small}
        cases.append(("hundred_real_files_comment_only", before,
                      {path: text + "\n# MDT comment-only control.\n" for path, text in before.items()}, False,
                      "100 distinct actual upstream Python files; only appended comments"))
        large = sorted([(path, raw) for path, raw in contents.items() if raw and path.endswith('.py') and 100 < len(raw) < 9000],
                       key=lambda item: (-len(item[1]), item[0]))[:100]
        before = {path: raw.decode('utf-8') for path, raw in large}
        cases.append(('hundred_larger_files_comment_only', before,
                      {path: text + '\n# MDT comment-only control.\n' for path, text in before.items()}, False,
                      '100 real larger Python files under the source budget; only appended comments'))
    return cases


def write_results(output, results):
    """Keep JSON and a small score matrix together, including explicit abstentions."""
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    fields = ["repo", "case", "analysis_scope", "risk", "debt", "confidence", "assessment_status",
              "expected_api_change", "api_change_flag", "api_flag_correct", "breaking_api_risk_flag", "contract_compatibility",
              "schema_compatibility", "semantic_change_count", "partial", "repeatable", "source_bytes", "error"]
    with (output / "scores.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results["experiments"])


async def run(output, cache):
    from api.projects import evaluate_job
    from core.registry import RegistryManager
    from services.git_analyzer import GitAnalyzer, is_supported_file
    from services.impact_engine import ImpactEngine
    from services.remediation_simulator import RemediationSimulator, compute_architecture_health, breakdown_smells
    from domain.architecture import GraphSnapshot, detect_smells, configured_thresholds
    original = copy.deepcopy(RegistryManager.load())
    results = {"method": "Current application core; immutable GitHub archives through transport adapter; controlled edits and one real upstream comparison, not actual incidents",
               "started_at": datetime.now(timezone.utc).isoformat(), "benchmark_schema_version": 2,
               "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "limitations": ["Source-only controls bypass ready-project HTTP admission after architecture abstention; no microservice debt is assigned",
                               "Compatibility labels are diagnostic synthetic mutations of public source, not held-out incident probabilities"],
               "python": platform.python_version(), "platform": platform.platform(), "cpu_limit": 2, "memory_limit_mib": 1024,
               "implementation_sha256": {path: hashlib.sha256((Path('/app') / path).read_bytes()).hexdigest() for path in
                   ['api/projects.py','services/git_analyzer.py','services/impact_engine.py','services/repo_onboarding.py',
                    'services/source_parser.py','services/analysis_evidence.py','domain/architecture.py']},
               "repositories": [], "experiments": [], "fetch_errors": [], "limits": {"files": 100, "source_bytes": 2097152, "per_file_bytes": 262144}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {repo: pool.submit(fetch_repository, repo, cache) for repo in REPOSITORIES}
        for repo, future in futures.items():
            try:
                metadata, contents = future.result()
            except Exception as error:
                results["fetch_errors"].append({"repo": repo, "error": str(error)})
                print(json.dumps({"fetch_failed": repo, "error": str(error)}), flush=True)
                continue
            project = {"id": "benchmark:" + repo, "name": repo, "repo_url": "https://github.com/" + repo,
                       "branch": metadata["sha"], "snapshot": {"services": [], "dependencies": [], "file_mappings": {}}}
            started = time.perf_counter()
            record = {**metadata, "architecture_status": "pending"}
            try:
                with patch("services.repo_onboarding.GitHubAPIClient", return_value=ArchiveTransport(contents)):
                    imported = await asyncio.wait_for(evaluate_job({"id": "import", "payload": {"project": project,
                        "input": {"source": "import", "head_ref": metadata["sha"]}}}), timeout=180)
                project = imported["project"]
                snapshot = project["snapshot"]
                with RegistryManager.use_snapshot(snapshot, project["id"]):
                    smells = detect_smells(GraphSnapshot.from_data(snapshot), configured_thresholds())
                    record.update(import_seconds=round(time.perf_counter()-started, 4), coverage=imported["coverage"],
                                  services=[service["name"] for service in snapshot["services"]],
                                  dependencies=snapshot["dependencies"], file_mappings=snapshot["file_mappings"],
                                  architecture=compute_architecture_health(breakdown_smells(smells)), smells=smells)
                    record["architecture_status"] = "imported"
                    record["partial"] = imported.get("partial_results", False)
                    record["warnings"] = imported.get("warnings", [])
                    record["evidence"] = imported.get("evidence", {})
                if repo == "GoogleCloudPlatform/microservices-demo":
                    detected = set(record["services"])
                    record["independent_topology_check"] = {"reference": "README architecture table: 11 named application services",
                        "expected": sorted(ONLINE_BOUTIQUE), "matched": sorted(detected & ONLINE_BOUTIQUE),
                        "missed": sorted(ONLINE_BOUTIQUE - detected), "extra": sorted(detected - ONLINE_BOUTIQUE),
                        "recall": len(detected & ONLINE_BOUTIQUE)/len(ONLINE_BOUTIQUE)}
            except Exception as error:
                abstained = isinstance(error, ValueError) and "Insufficient architecture evidence" in str(error)
                record.update(import_error=str(error), import_seconds=round(time.perf_counter()-started, 4),
                              architecture_status="abstained" if abstained else "failed", architecture=None,
                              services=[], dependencies=[], file_mappings={})
                print(json.dumps({"import_failed": repo, "error": str(error)}), flush=True)
                # Deliberate parser/core controls only: an empty graph is never
                # represented as discovered microservices or a debt score.
                snapshot = {"services": [], "dependencies": [], "file_mappings": {},
                            "coverage": {"warnings": ["architecture_unavailable_source_only_control"]},
                            "project": {"repo_url": project["repo_url"], "revision": metadata["sha"],
                                        "source": "benchmark_source_only"}}
                project["snapshot"] = snapshot
            print(json.dumps({"import": repo, "services": len(record["services"]), "edges": len(record["dependencies"]),
                              "debt": record["architecture"]["score"] if record["architecture"] else None,
                              "files_read": record.get("coverage", {}).get("files_read"),
                              "architecture_status": record["architecture_status"]}), flush=True)
            results["repositories"].append(record)
            try:
                cases = experiment_cases(repo, contents)
                if repo == 'expressjs/express':
                    base_metadata, base_contents = await asyncio.to_thread(fetch_repository, repo, cache,
                        '1faf228935aa0a13111f92c28ee795be64ce3f0f')
                    paths = [path for path in sorted(base_contents.keys() | contents.keys()) if is_supported_file(path)
                             and base_contents.get(path) != contents.get(path)]
                    before = {path: source(base_contents, path) for path in paths if path in base_contents and base_contents[path] is not None}
                    after = {path: source(contents, path) for path in paths if path in contents and contents[path] is not None}
                    cases.append(('real_upstream_4_21_2_to_pinned_HEAD', before, after, None,
                                  'Actual upstream source comparison from ' + base_metadata['sha'] + ' to ' + metadata['sha'] + '; no binary incident label'))
                    core_paths = {path for path in paths if path.startswith('lib/') or path in {'index.js', 'package.json'}}
                    cases.append(('real_upstream_core_subset', {path:text for path,text in before.items() if path in core_paths},
                                  {path:text for path,text in after.items() if path in core_paths}, None,
                                  'Actual Express 4.21.2 to pinned HEAD lib/, index.js and package.json changes only; explicitly not the whole release'))
                    record['real_comparison_base'] = base_metadata
            except Exception as error:
                results["experiments"].append({"repo": repo, "setup_error": str(error)})
                continue
            for name, before, after, expected_api, rationale in cases:
                measurement = {"repo": repo, "case": name, "upstream_sha": metadata["sha"], "expected_api_change": expected_api,
                               "analysis_scope": "imported_project_core" if record["architecture_status"] == "imported" else "source_only_core_evaluation",
                               "rationale": rationale, "paths": sorted(before.keys() | after.keys()),
                               "source_bytes": sum(len(text.encode()) for text in list(before.values()) + list(after.values()))}
                base_ref = record['real_comparison_base']['sha'] if name.startswith('real_upstream') else metadata['sha']
                measurement['base_sha'] = base_ref
                job = {"id": name, "payload": {"project": project,
                    "input": {"source": "patch", "base_ref": base_ref, "head_ref": metadata["sha"],
                              "before_files": before, "after_files": after}}}
                started = time.perf_counter()
                try:
                    first = await asyncio.wait_for(evaluate_job(copy.deepcopy(job)), timeout=180)
                    second = await asyncio.wait_for(evaluate_job(copy.deepcopy(job)), timeout=180)
                    with RegistryManager.use_snapshot(snapshot, project["id"]):
                        local = [{"file_path": path, "old_content": before.get(path, ""), "new_content": after.get(path, ""),
                                  "change_type": "added" if path not in before else "deleted" if path not in after else "modified"}
                                 for path in sorted(before.keys() | after.keys()) if before.get(path) != after.get(path)]
                        changes = GitAnalyzer().analyze_local_changes(local, base_sha=base_ref, commit_sha=metadata["sha"],
                            source_context={"before": before, "after": after})
                        engine = ImpactEngine()
                        factors = engine._calculate_deterministic_risk(changes)
                        api_changed = engine._has_api_changes(changes)
                        # Unsupported library topology has no architecture preview.
                        # The source-only control intentionally bypasses normal
                        # project admission, so do not call a project preview API.
                        preview = (await RemediationSimulator().simulate_fix([], snapshot_version=first["snapshot_version"])
                                   if record["architecture_status"] == "imported" else None)
                    stable_fields = ["risk_score", "architecture_smell_score", "smells", "coverage", "affected_files", "snapshot_version",
                                     "confidence", "confidence_evidence", "assessment_status", "evidence"]
                    stable_fields = [key for key in stable_fields if key in first]
                    linked_contracts = [entry for c in changes for entry in c.ast_metadata.get("schema_changes", {}).get("affected_routes", [])]
                    contract_compatibility = sorted({entry.get("compatibility", "not_reported") for entry in
                        [c.ast_metadata.get("contract_changes", {}) for c in changes] + linked_contracts})
                    schema_compatibility = sorted({c.ast_metadata.get("schema_changes", {}).get("compatibility", "not_reported") for c in changes})
                    measurement.update(risk=first["risk_score"], severity=first["severity"],
                        debt=first["architecture_smell_score"] if record["architecture_status"] == "imported" else None,
                        confidence=first["confidence"], impacted_services=first["impacted_services"], partial=first["partial_results"],
                        confidence_evidence=first.get("confidence_evidence"), assessment_status=first.get("assessment_status"),
                        evidence=first.get("evidence", {}), contract_compatibility=contract_compatibility,
                        schema_compatibility=schema_compatibility,
                        linked_contract_changes=linked_contracts,
                        semantic_change_count=sum(c.ast_metadata.get("semantic_change") is True for c in changes),
                        semantic_unknown_count=sum(c.ast_metadata.get("semantic_change") is None for c in changes),
                        semantic_statuses={c.file_path: c.ast_metadata.get("semantic_status") for c in changes},
                        warnings=first["warnings"], coverage=first["coverage"], affected_files=first["affected_files"],
                        api_change_flag=api_changed, api_flag_correct=api_changed == expected_api if expected_api is not None else None,
                        breaking_api_risk_flag=factors.api_changes,
                        changed_contract_count=sum(len(c.ast_metadata.get("contract_changes", {}).get(kind, [])) for c in changes for kind in ("added", "removed", "modified")),
                        repeatable=all(first[key] == second[key] for key in stable_fields),
                        no_edit_preview_unchanged=preview["before"] == preview["after"] if preview else None,
                        python_ast_unchanged=(all(ast.dump(ast.parse(before[path])) == ast.dump(ast.parse(after[path])) for path in before)
                                              if "comment_only" in name and all(path.endswith(".py") for path in before) else None),
                        seconds_two_runs=round(time.perf_counter()-started, 4),
                        result_sha256=hashlib.sha256(json.dumps({key:first[key] for key in stable_fields}, sort_keys=True).encode()).hexdigest())
                    print(json.dumps({key: measurement[key] for key in ("repo", "case", "risk", "debt", "partial", "api_flag_correct", "repeatable")}), flush=True)
                except Exception as error:
                    measurement["error"] = str(error)
                    print(json.dumps({"case_failed": name, "error": str(error)}), flush=True)
                results["experiments"].append(measurement)
                write_results(output, results)
    results["registry_unchanged"] = RegistryManager.load() == original
    results['peak_process_rss_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3)
    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_results(output, results)
    if not results["registry_unchanged"]:
        raise AssertionError("The global registry changed during the benchmark")
    print(json.dumps({"completed": True, "repositories": len(results["repositories"]), "experiments": len(results["experiments"]),
                      "registry_unchanged": results["registry_unchanged"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/benchmark-output"))
    parser.add_argument("--cache", type=Path, help="Existing immutable archive cache; defaults to output")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace result files in the output directory")
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    if (arguments.output / "results.json").exists() and not arguments.overwrite:
        parser.error("Result file already exists; select a new --output directory to preserve the prior run")
    archive_cache = arguments.cache or arguments.output
    archive_cache.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(arguments.output, archive_cache))
