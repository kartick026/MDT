"""Owned projects, durable jobs and immutable analysis results for all clients."""
import asyncio
import copy
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.auth import get_current_user
from core.config import settings
from core.registry import RegistryManager, DEFAULT_REGISTRY, LOCAL_DEMO_SMELL_HISTORY
from core.store import get_store, IdempotencyConflict, ProjectNotFound
from domain.architecture import GraphSnapshot, DETECTOR_VERSION, detect_smells, configured_thresholds
from domain.drift import compare_snapshots, snapshot_metadata
from domain.policies import evaluate_policies, policy_version
from services.remediation_simulator import GraphEdit, RemediationSimulator, compute_architecture_health, breakdown_smells, generate_edits_for_smells, apply_snapshot_edits

logger = logging.getLogger(__name__)
router = APIRouter()


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    repo_url: str = Field(max_length=300)
    branch: str = Field(default="main", min_length=1, max_length=200)
    use_demo: bool = False

    @field_validator("repo_url")
    @classmethod
    def github_only(cls, value):
        value = value.strip().rstrip("/")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError("Use an HTTPS github.com owner/repository URL without credentials or query parameters")
        return value.removesuffix(".git")

    @field_validator("branch")
    @classmethod
    def safe_ref(cls, value):
        if value.startswith("-") or any(ch.isspace() for ch in value) or any(ch in value for ch in ("\x00", "~", "^", ":", "?", "*", "[", "\\")) or ".." in value:
            raise ValueError("Invalid branch reference")
        return value


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["commit", "patch", "import"] = "commit"
    base_ref: str | None = Field(default=None, max_length=200)
    head_ref: str | None = Field(default=None, max_length=200)
    comparison_mode: Literal["direct", "merge_base"] = "direct"
    patch: str | None = Field(default=None, max_length=2*1024*1024)
    before_files: dict[str, str] | None = None
    after_files: dict[str, str] | None = None
    local_changes: list[dict] | None = Field(default=None, max_length=100)
    changed_files: list[str] | None = Field(default=None, max_length=100)
    snapshot_version: str | None = None
    pull_request: int | None = Field(default=None, ge=1, le=100000000)

    @model_validator(mode="after")
    def bound_source(self):
        if len(json.dumps(self.model_dump()).encode()) > 3*1024*1024:
            raise ValueError("Source input exceeds 3 MiB")
        if self.local_changes is not None and (self.before_files is not None or self.after_files is not None):
            raise ValueError("Submit one source representation: local_changes or before_files/after_files")
        if self.source == "patch" and self.local_changes is None and self.before_files is None and self.after_files is None:
            raise ValueError("Patch analysis requires before_files/after_files or local_changes; a patch alone is incomplete source evidence")
        if self.source == "patch" and self.local_changes is None and (self.before_files is None or self.after_files is None):
            raise ValueError("Both before_files and after_files are required; use an explicit empty object for additions/deletions")
        if self.source == "patch" and not self.base_ref:
            raise ValueError("Patch snapshots require an explicit base_ref")
        if self.source != "patch" and (self.local_changes is not None or self.before_files is not None or self.after_files is not None or self.patch is not None):
            raise ValueError("Use source=patch for submitted source snapshots")
        if self.pull_request and self.source != "commit":
            raise ValueError("Pull request analysis requires source=commit")
        for ref in (self.base_ref, self.head_ref):
            if ref and (ref.startswith("-") or "\x00" in ref or len(ref.split()) != 1):
                raise ValueError("Invalid revision")
        return self


class PreviewInput(BaseModel):
    edits: list[GraphEdit] = Field(max_length=100)
    snapshot_version: str | None = None


class FindingReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: Literal["confirmed", "false_positive", "accepted_risk", "unreviewed"]
    reason: str = Field(min_length=3, max_length=2000)
    expires_days: int = Field(default=30, ge=1, le=90)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Provide a review reason")
        return value.strip()


class DependencyRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["require", "forbid"]
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=500)


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[DependencyRule] = Field(max_length=50)

    @model_validator(mode="after")
    def unique_pairs(self):
        pairs = [(rule.source, rule.target) for rule in self.rules]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Use one dependency rule per source/target pair")
        return self


class BaselineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_version: str = Field(min_length=1, max_length=100)


def _owner(user):
    return user.username


def _analyst(user):
    if user.role not in {"admin", "analyst"}:
        raise HTTPException(403, "A private-beta analyst account is required")
    return user.username


def _project(ident, owner):
    project = get_store().get("project", ident, owner)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _public_project(project):
    return {k: v for k, v in project.items() if k != "snapshot"}


def _captured_snapshot(project, version, owner):
    record = get_store().get("snapshot", project["id"] + ":" + version, owner)
    if record:
        return record
    # Read compatibility for projects imported before immutable archives existed.
    if project.get("ready") and project.get("snapshot_version") == version and project.get("snapshot"):
        return {"project_id": project["id"], "snapshot_version": version, "snapshot": project["snapshot"],
                "captured_at": None, "source_analysis_id": None, "coverage": project["snapshot"].get("coverage", {})}
    raise HTTPException(404, "Captured snapshot not found")


def _demo_snapshot():
    data = copy.deepcopy(DEFAULT_REGISTRY)
    # The deliberately unresolved demo target is evidence of a broken dependency,
    # not a fifth deployed member of the four-service fleet.
    for service in data["services"]:
        if service["name"] == "inventory-service":
            service.update(node_type="external", is_external=True)
    data.update(copy.deepcopy(LOCAL_DEMO_SMELL_HISTORY))
    return data


@router.get("/demo")
def public_demo():
    snapshot = GraphSnapshot.from_data(_demo_snapshot(), source="illustrative_demo")
    smells = detect_smells(snapshot, configured_thresholds())
    health = compute_architecture_health(breakdown_smells(smells), snapshot)
    recommendations = []
    # Only fixed fixture recommendations are computed publicly. No submitted
    # source, arbitrary graph, database access or network request is involved.
    templates = [
        ("rec-circular", "Circular Dependency", "Preview removing a cycle edge", "Remove one recorded cycle connection, then inspect resolved and introduced findings. Application contracts still need validation."),
        ("rec-database", "Shared Database", "Preview a shared-data interface", "Route direct database callers through an explicit interface. This models topology only; it does not implement data ownership or migrations."),
        ("rec-circuit", "Missing Circuit Breaker", "Preview recorded circuit-breaker protection", "Mark one service as hypothetically protected. Runtime resilience is not verified by a graph property."),
    ]
    with RegistryManager.use_snapshot(snapshot.to_data(), "public-demo"):
        for ident, kind, title, description in templates:
            finding = next((item for item in smells if item["type"] == kind), None)
            if not finding:
                continue
            edits = generate_edits_for_smells([finding])
            after, removed = apply_snapshot_edits(snapshot, edits)
            measured = RemediationSimulator._result(snapshot, after, edits, removed, None, None, "snapshot")
            recommendations.append({"id": ident, "title": title, "description": description,
                "finding_ids": [finding["id"]], "edits": [edit.model_dump(exclude_none=True) for edit in edits],
                "recorded_preview": measured})
    return {"status": "demo", "label": "Illustrative academic demo; recorded fixture history, no live analysis",
            "snapshot": snapshot.to_data(), "snapshot_version": snapshot.version,
            "smells": smells, "architecture_health": health, "suggested_fixes": recommendations,
            "architecture_smell_score": health["score"], "architecture_smells_count": health["total_smells"],
            "evidence": {"mode": "illustrative_demo", "semantic_used": False, "detector_version": DETECTOR_VERSION}}


@router.get("/projects")
def list_projects(user=Depends(get_current_user)):
    return {"projects": [_public_project(p) for p in get_store().list("project", _owner(user))]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, user=Depends(get_current_user)):
    owner = _analyst(user)
    store = get_store()
    ident = uuid.uuid4().hex
    snapshot = _demo_snapshot() if body.use_demo else {"services": [], "dependencies": [], "file_mappings": {}}
    if body.use_demo and RegistryManager.repository_key(body.repo_url) != RegistryManager.repository_key(settings.DEMO_REPO_URL):
        raise HTTPException(422, "Demo topology can only be attached to the configured demo repository")
    snapshot["project"] = {"repo_url": body.repo_url, "repository_key": RegistryManager.repository_key(body.repo_url), "branch": body.branch, "source": "illustrative_demo" if body.use_demo else "repository"}
    project = {"id": ident, "name": body.name.strip(), "repo_url": body.repo_url, "branch": body.branch,
               "role": "owner", "created_at": datetime.now(timezone.utc).isoformat(), "snapshot": snapshot,
               "snapshot_version": GraphSnapshot.from_data(snapshot).version, "ready": body.use_demo}
    try:
        store.create_project(owner, project)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc
    result = _public_project(project)
    if not body.use_demo:
        try:
            result["job_id"] = store.enqueue(owner, ident, {"input": {"source": "import"}, "project": project}, require_project=True)
        except ProjectNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            store.delete_project(ident, owner)
            raise HTTPException(429, str(exc)) from exc
    return result


@router.get("/projects/{project_id}")
def read_project(project_id: str, user=Depends(get_current_user)):
    return _project(project_id, _owner(user))


@router.get("/projects/{project_id}/snapshots")
def list_snapshots(project_id: str, user=Depends(get_current_user)):
    owner = _owner(user)
    project = _project(project_id, owner)
    store = get_store()
    baseline = store.get("baseline", project_id, owner)
    baseline_version = baseline["baseline_version"] if baseline else None
    snapshots = store.snapshot_metadata(project_id, owner)
    versions = {item["snapshot_version"] for item in snapshots}
    # Always include the current capture and pinned baseline, including older data.
    for version in (project.get("snapshot_version") if project.get("ready") else None, baseline_version):
        if version and version not in versions:
            record = _captured_snapshot(project, version, owner)
            snapshots.append({**snapshot_metadata(record), "coverage": record.get("coverage", {})})
            versions.add(version)
    for item in snapshots:
        item["baseline"] = item["snapshot_version"] == baseline_version
    return {"snapshots": snapshots, "baseline_version": baseline_version}


@router.put("/projects/{project_id}/baseline")
def select_baseline(project_id: str, body: BaselineInput, user=Depends(get_current_user)):
    owner = _analyst(user)
    try:
        return get_store().set_project_baseline(project_id, owner, body.snapshot_version)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/projects/{project_id}/drift")
def project_drift(project_id: str, base_version: str | None = Query(default=None, max_length=100),
                  target_version: str | None = Query(default=None, max_length=100), user=Depends(get_current_user)):
    owner = _owner(user)
    project = _project(project_id, owner)
    if base_version is None:
        baseline = get_store().get("baseline", project_id, owner)
        if not baseline:
            raise HTTPException(409, "Select a captured snapshot as the project baseline first")
        base_version = baseline["baseline_version"]
    target_version = target_version or project.get("snapshot_version")
    if not target_version:
        raise HTTPException(409, "Import an architecture snapshot first")
    before = _captured_snapshot(project, base_version, owner)
    after = _captured_snapshot(project, target_version, owner)
    try:
        return {"project_id": project_id, **compare_snapshots(before, after)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user=Depends(get_current_user)):
    owner = _analyst(user)
    _project(project_id, owner)
    get_store().delete_project(project_id, owner)


@router.get("/projects/{project_id}/policies")
def read_policies(project_id: str, user=Depends(get_current_user)):
    owner = _owner(user)
    project = _project(project_id, owner)
    rules = (get_store().get("policy", project_id, owner) or {}).get("rules", [])
    return {"rules": rules, "evaluation": evaluate_policies(project["snapshot"], rules)}


@router.put("/projects/{project_id}/policies")
def save_policies(project_id: str, body: PolicyInput, user=Depends(get_current_user)):
    owner = _analyst(user)
    project = _project(project_id, owner)
    rules = [rule.model_dump() for rule in body.rules]
    data = {"rules": rules, "version": policy_version(rules), "updated_at": time.time()}
    try:
        get_store().put_project_record("policy", project_id, owner, project_id, data)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return {**data, "evaluation": evaluate_policies(project["snapshot"], rules)}


@router.post("/projects/{project_id}/analyses", status_code=202)
def submit_analysis(project_id: str, body: AnalysisInput, user=Depends(get_current_user), idempotency_key: str | None = Header(default=None, max_length=200)):
    owner = _analyst(user)
    project = _project(project_id, owner)
    if body.source != "import" and not project["ready"]:
        raise HTTPException(409, "Wait for architecture import to finish")
    if body.snapshot_version and body.snapshot_version != project["snapshot_version"]:
        raise HTTPException(409, "Architecture snapshot changed; reload the project")
    payload = {"input": body.model_dump(exclude_none=True), "project": project,
               "policy": get_store().get("policy", project_id, owner) or {"rules": []}}
    dedupe = hashlib.sha256(f"{owner}:{project_id}:{idempotency_key}".encode()).hexdigest() if idempotency_key else None
    try:
        fingerprint = hashlib.sha256(json.dumps(body.model_dump(exclude_none=True), sort_keys=True).encode()).hexdigest()
        ident = get_store().enqueue(owner, project_id, payload, dedupe, fingerprint, require_project=True)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc
    job = get_store().job(ident, owner)
    if job is None:
        raise HTTPException(404, "Project or analysis was deleted during submission")
    return {"job_id": ident, "status": job["status"]}


@router.get("/analyses")
def list_analyses(project_id: str | None = Query(default=None, max_length=100),
                  status: Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"] | None = None,
                  q: str = Query(default="", max_length=200), limit: int = Query(default=20, ge=1, le=100),
                  offset: int = Query(default=0, ge=0, le=100000), user=Depends(get_current_user)):
    owner = _owner(user)
    if project_id:
        _project(project_id, owner)
    return get_store().list_jobs(owner, project_id, status, q.strip(), limit, offset)


@router.get("/analyses/{job_id}/snapshot")
def get_analysis_snapshot(job_id: str, user=Depends(get_current_user)):
    owner = _owner(user)
    job = get_store().job(job_id, owner)
    result = job.get("result") if job else None
    if not result:
        raise HTTPException(404, "Completed analysis snapshot not found")
    snapshot = result.get("_snapshot") or result.get("project", {}).get("snapshot")
    if not snapshot or not result.get("snapshot_version"):
        raise HTTPException(404, "Completed analysis snapshot not found")
    return {"analysis_id": job_id, "project_id": job["project"], "snapshot_version": result["snapshot_version"],
            "snapshot": snapshot, "coverage": snapshot.get("coverage", {})}


@router.get("/analyses/{job_id}/reviews")
def finding_reviews(job_id: str, user=Depends(get_current_user)):
    store, owner = get_store(), _owner(user)
    job = store.job(job_id, owner)
    if not job:
        raise HTTPException(404, "Analysis not found")
    rows = store.list("finding_review:" + job_id, owner, job["project"], limit=2000)
    return {"reviews": [{**row, "expired": row["expires_at"] <= time.time()} for row in rows],
            "score_effect": "none"}


@router.put("/analyses/{job_id}/reviews/{finding_id}")
def review_finding(job_id: str, finding_id: str, body: FindingReviewInput, user=Depends(get_current_user)):
    store, owner = get_store(), _analyst(user)
    job = store.job(job_id, owner)
    if not job:
        raise HTTPException(404, "Analysis not found")
    result = job.get("result") or {}
    findings = result.get("smells", result.get("findings", []))
    if not any(finding.get("id") == finding_id for finding in findings):
        raise HTTPException(404, "Finding not present in this saved analysis")
    now = time.time()
    record = {"analysis_id": job_id, "finding_id": finding_id, "classification": body.classification,
              "reason": body.reason, "reviewed_by": owner, "updated_at": now,
              "expires_at": now + body.expires_days * 86400, "score_effect": "none"}
    try:
        store.put_project_record("finding_review:" + job_id, job_id + ":" + finding_id, owner, job["project"], record)
    except ProjectNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return {**record, "expired": False}


@router.get("/jobs/{job_id}")
@router.get("/analyses/{job_id}")
def get_job(job_id: str, user=Depends(get_current_user)):
    job = get_store().job(job_id, _owner(user))
    if not job:
        raise HTTPException(404, "Analysis not found")
    _expose_captured_coverage(job)
    return job


def _expose_captured_coverage(job):
    """Expose the saved scan separately from changed-file extraction.

    Old analyses already hold their immutable topology inside _snapshot. Read
    that capture, never the project's latest import, and do not rewrite history.
    """
    result = job.get("result")
    if result:
        snapshot = result.pop("_snapshot", None)
        if "topology_coverage" not in result and isinstance(snapshot, dict):
            result["topology_coverage"] = snapshot.get("coverage", {})


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str, user=Depends(get_current_user)):
    owner = _analyst(user)
    job = get_store().cancel(job_id, owner)
    if not job:
        raise HTTPException(404, "Analysis not found")
    _expose_captured_coverage(job)
    return job


@router.post("/analyses/{job_id}/previews")
async def preview(job_id: str, body: PreviewInput, user=Depends(get_current_user)):
    owner = _analyst(user)
    job = await asyncio.to_thread(get_store().job, job_id, owner)
    if not job or not job.get("result") or job["result"].get("kind") == "import":
        raise HTTPException(404, "Completed analysis not found")
    result = job["result"]
    if body.snapshot_version and body.snapshot_version != result["snapshot_version"]:
        raise HTTPException(409, "Preview snapshot does not match the saved analysis")
    try:
        with RegistryManager.use_snapshot(result["_snapshot"], job["project"]):
            return await RemediationSimulator().simulate_fix(body.edits, snapshot_version=result["snapshot_version"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


async def evaluate_job(job):
    """Shared deterministic core: extensions and web use the same code path."""
    from services.git_analyzer import GitAnalyzer
    from services.impact_engine import ImpactEngine
    from services.repo_onboarding import RepoOnboarder
    project, request = job["payload"]["project"], job["payload"]["input"]
    if settings.RUNTIME_PROFILE == "hosted" and request["source"] != "patch":
        import httpx
        # Beta accounts do not inherit the deployment operator's private-repo token.
        repo_path = project["repo_url"].removeprefix("https://github.com/")
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(f"https://api.github.com/repos/{repo_path}")
            if response.status_code != 200 or response.json().get("private", True):
                raise ValueError("Hosted alpha supports publicly accessible GitHub repositories only")
    with RegistryManager.use_snapshot(project["snapshot"], project["id"]):
        if request["source"] == "import":
            imported = await RepoOnboarder().import_from_repo(project["repo_url"], request.get("head_ref") or project["branch"])
            snapshot = RegistryManager.load()
            if not snapshot.get("services"):
                raise ValueError("No architecture could be inferred from this repository")
            graph = GraphSnapshot.from_data(snapshot)
            smells = detect_smells(graph, configured_thresholds())
            health = compute_architecture_health(breakdown_smells(smells), graph)
            project.update(snapshot=snapshot, snapshot_version=graph.version, ready=True)
            return {"kind": "import", "project": project, "snapshot_version": graph.version,
                    "policy_assessment": evaluate_policies(snapshot, job["payload"].get("policy", {}).get("rules", [])),
                    "commit_sha": imported.get("revision", snapshot.get("project", {}).get("revision")),
                    "partial_results": imported.get("status") == "partial", "coverage": imported.get("coverage", {}),
                    "architecture_health": health, "architecture_smell_score": health["score"],
                    "smells": smells, "risk_score": None,
                    "evidence": {"mode": "repository_import", "semantic_used": False,
                                 "score_interpretation": "Measured static architectural debt; no commit risk assessed"},
                    "warnings": imported.get("coverage", {}).get("warnings", [])}
        analyzer = GitAnalyzer()
        if request.get("pull_request"):
            import httpx
            repo_path = project["repo_url"].removeprefix("https://github.com/")
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await analyzer._gh._request_with_retry(client, f"https://api.github.com/repos/{repo_path}/pulls/{request['pull_request']}")
                if response.status_code != 200:
                    raise ValueError("Pull request metadata is unavailable")
                metadata = response.json()
                request = {**request, "base_ref": metadata["base"]["sha"], "head_ref": metadata["head"]["sha"], "comparison_mode": "merge_base"}
        local = request.get("local_changes")
        source_context = None
        if request["source"] == "patch" and local is None:
            before, after = request.get("before_files") or {}, request.get("after_files") or {}
            source_context = {"before": before, "after": after}
            local = [{"file_path": path, "old_content": before.get(path, ""), "new_content": after.get(path, ""),
                      "change_type": "added" if path not in before else "deleted" if path not in after else "modified"}
                     for path in sorted(before.keys() | after.keys()) if before.get(path) != after.get(path)]
        changes = await analyzer.analyze_push(project["repo_url"], request.get("head_ref") or project["branch"],
            request.get("changed_files"), base_sha=request.get("base_ref"),
            comparison_mode=request.get("comparison_mode", "direct"), local_changes=local,
            source_context=source_context)
        engine = ImpactEngine()
        impact = await engine.analyze_impact(changes, commit_sha=request.get("head_ref"))
        snapshot = RegistryManager.load()
        graph = GraphSnapshot.from_data(snapshot)
        smells = detect_smells(graph, configured_thresholds())
        health = compute_architecture_health(breakdown_smells(smells), graph)
        extraction = getattr(analyzer, "last_extraction", {})
        warnings = list(extraction.get("warnings", []))
        warnings.extend("topology:" + warning for warning in snapshot.get("coverage", {}).get("warnings", []))
        warnings.extend(impact.confidence_evidence.get("reasons", []))
        partial = extraction.get("status") == "partial" or any(getattr(c, "extraction_status", "complete") == "partial" for c in changes)
        partial = partial or bool(snapshot.get("coverage", {}).get("warnings"))
        partial = partial or impact.assessment_status in {"insufficient_evidence", "partial"}
        if not changes:
            warnings.append("No changed files were found; this is not a deployment safety assessment")
        fixes = await engine.explainer.suggest_remediation_with_edits(smells=smells, impacted_services=impact.impacted_services, changes=changes, risk_score=impact.risk_score, connection_bugs=[])
        return {**impact.model_dump(mode="json"), "kind": "analysis", "analysis_id": job["id"], "project_id": project["id"],
                "affected_files": [{**impact.affected_files[index].model_dump(mode="json"),
                    "previous_path": getattr(change, "previous_path", None),
                    "extraction_status": getattr(change, "extraction_status", "partial"),
                    "extraction_warnings": getattr(change, "extraction_warnings", []),
                    "parser_coverage": getattr(change, "parser_coverage", "unknown"),
                    "base_sha": getattr(change, "base_sha", None), "commit_sha": getattr(change, "commit_sha", None),
                    "contract_changes": getattr(change, "ast_metadata", {}).get("contract_changes", {}),
                    "schema_changes": getattr(change, "ast_metadata", {}).get("schema_changes", {}),
                    "semantic_change": getattr(change, "ast_metadata", {}).get("semantic_change"),
                    "semantic_status": getattr(change, "ast_metadata", {}).get("semantic_status", "unknown")}
                    for index, change in enumerate(changes)],
                "repo_url": project["repo_url"], "commit_sha": extraction.get("head_sha", request.get("head_ref")),
                "base_sha": extraction.get("base_sha", request.get("base_ref")),
                "timestamp": datetime.now(timezone.utc).isoformat(), "snapshot_version": graph.version,
                "smells": smells, "architecture_health": health, "suggested_fixes": fixes,
                "architecture_smell_score": health["score"], "architecture_smells_count": health["total_smells"],
                "architecture_smells_breakdown": breakdown_smells(smells),
                "partial_results": partial, "warnings": warnings, "coverage": extraction,
                "topology_coverage": snapshot.get("coverage", {}),
                "policy_assessment": evaluate_policies(snapshot, job["payload"].get("policy", {}).get("rules", [])),
                "evidence": {"mode": "deterministic_snapshot", "semantic_used": False, "detector_version": DETECTOR_VERSION,
                             "topology_source": project["snapshot"].get("project", {}).get("source"),
                             "topology_revision": project["snapshot"].get("project", {}).get("revision"),
                             "topology_reextracted": False,
                             "confidence_kind": "evidence_completeness",
                             "confidence_calibrated": False,
                             "score_interpretation": "Engineering indicator; not a calibrated incident probability"},
                "_snapshot": snapshot}


async def run_worker():
    """One bounded worker per process; leases support restart recovery."""
    store = get_store()
    last_prune = 0
    while True:
        try:
            if time.time() - last_prune > 3600:
                await asyncio.to_thread(store.prune)
                last_prune = time.time()
            job = await asyncio.to_thread(store.claim)
            if not job:
                await asyncio.sleep(1)
                continue
            task = asyncio.create_task(evaluate_job(job))
            started = time.monotonic()
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=10)
                    if not await asyncio.to_thread(store.heartbeat, job):
                        task.cancel()
                        break
                    if time.monotonic() - started > settings.JOB_TIMEOUT_SECONDS:
                        task.cancel()
                        await asyncio.to_thread(store.finish, job, error="Job timed out; reduce the change size and retry")
                        break
                if not task.cancelled() and task.done():
                    result = task.result()
                    await asyncio.to_thread(store.finish, job, result=result)
            except asyncio.CancelledError:
                task.cancel()
                raise
            except Exception as exc:
                logger.exception("Analysis job %s failed", job["id"])
                error = str(exc)[:500] if isinstance(exc, ValueError) else "Analysis failed; verify repository access, revisions and source limits"
                await asyncio.to_thread(store.finish, job, error=error)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker persistence error; retrying")
            await asyncio.sleep(5)
