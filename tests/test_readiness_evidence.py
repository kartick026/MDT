"""The release gate must reject incomplete proof, even when a status says pass."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts.evaluate_accuracy import evaluate, summarize
from scripts import professional_readiness as gate
from scripts.readiness_common import ROOT, digest_file


@pytest.fixture
def targets():
    return json.loads((ROOT / "readiness-policy.json").read_text())["accuracy"]


def test_abstaining_on_positive_does_not_inflate_recall(targets):
    rows = [{"family": "semantic_change", "expected": e, "predicted": p}
            for e, p in ((True, True), (True, None), (False, True), (False, False))]
    metrics = summarize(rows, ["semantic_change"], targets)["semantic_change"]
    assert metrics["precision"] == .5
    assert metrics["recall"] == .5
    assert metrics["prediction_coverage"] == .75
    assert metrics["abstained_positive"] == 1
    assert metrics["precision_interval_95"][0] < .5 < metrics["precision_interval_95"][1]
    assert not metrics["meets_targets"]


def test_empty_metrics_are_unknown_not_perfect(targets):
    result = summarize([], targets["families"], targets)
    assert all(m["precision"] is None and m["recall"] is None and not m["meets_targets"] for m in result.values())


@pytest.mark.parametrize("change", ["empty", "duplicate", "invalid-label", "unknown-family"])
def test_bad_evaluation_dataset_is_rejected(targets, change):
    case = {"id": "one", "family": "semantic_change", "expected": True, "changes": [{}]}
    cases = [case]
    if change == "empty":
        cases = []
    elif change == "duplicate":
        cases *= 2
    elif change == "invalid-label":
        case["expected"] = 1
    else:
        case["family"] = "invented"
    with pytest.raises(ValueError):
        evaluate({"schema_version": 1, "split": "development", "cases": cases}, targets, lambda _: True)


def test_development_controls_use_the_real_parser(targets):
    data = json.loads((ROOT / "evaluation/development.json").read_text())
    result = evaluate(data, targets)
    assert result["controls_passed"]
    assert result["case_count"] == len(data["cases"])
    assert not result["meets_statistical_targets"]


@pytest.fixture
def evidence_root(tmp_path, monkeypatch):
    (tmp_path / "readiness-policy.json").write_bytes((ROOT / "readiness-policy.json").read_bytes())
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation/tuning-repositories.json").write_bytes((ROOT / "evaluation/tuning-repositories.json").read_bytes())
    monkeypatch.setattr(gate, "source_identity", lambda root: {"sha256": "current", "files": 10})
    return tmp_path


def write_evidence(root, report):
    path = root / "report.json"
    path.write_text(json.dumps(report))
    return {"schema_version": 1, "evidence": {"security": {"path": path.name, "sha256": digest_file(path)}}}


def security_report():
    return {"schema_version": 1, "kind": "security", "status": "passed", "source": {"sha256": "current"},
            "created_at": datetime.now(timezone.utc).isoformat(), "review_type": "independent",
            "reviewer": "fixture reviewer", "open_high_critical": 0,
            "checks": [{"name": name, "passed": True} for name in (
                "account-isolation", "source-upload", "untrusted-repository", "credentials", "deletion", "abuse", "dependency-scan")]}


def test_empty_manifest_and_missing_metadata_cannot_pass(evidence_root):
    result = gate.check_professional({"schema_version": 1, "evidence": {}}, {}, evidence_root)
    assert not result["professional_ready"]
    assert len(result["gates"]) == 6
    assert all(not check["passed"] for check in result["gates"])
    assert result["metadata_remaining"]


@pytest.mark.parametrize("fault", ["stale", "future", "different-source", "tamper", "missing-check", "boolean-count", "wrong-kind"])
def test_invalid_or_stale_evidence_cannot_pass(evidence_root, fault):
    report = security_report()
    if fault == "stale":
        report["created_at"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    elif fault == "future":
        report["created_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif fault == "different-source":
        report["source"]["sha256"] = "old-build"
    elif fault == "missing-check":
        report["checks"].pop()
    elif fault == "boolean-count":
        report["open_high_critical"] = False
    elif fault == "wrong-kind":
        report["kind"] = "local_reliability"
    manifest = write_evidence(evidence_root, report)
    if fault == "tamper":
        (evidence_root / "report.json").write_text("{}")
    result = gate.check_professional(manifest, {}, evidence_root)
    security = next(g for g in result["gates"] if g["gate"] == "security")
    assert not security["passed"]
    assert not result["professional_ready"]


def test_valid_single_gate_does_not_clear_other_gates(evidence_root):
    result = gate.check_professional(write_evidence(evidence_root, security_report()), {}, evidence_root)
    assert next(g for g in result["gates"] if g["gate"] == "security")["passed"]
    assert not result["professional_ready"]


def test_evidence_path_cannot_escape_checkout(evidence_root):
    with pytest.raises(ValueError, match="inside this checkout"):
        gate.safe_artifact(evidence_root, {"path": "../secret.json", "sha256": "irrelevant"})


def test_local_recovery_does_not_satisfy_deployed_operations(evidence_root):
    policy = json.loads((evidence_root / "readiness-policy.json").read_text())
    errors = gate.gate_errors("operations", {"environment": "disposable_local_sqlite", "status": "passed"},
                             policy, {"api_url": "https://api.mdt.invalid"}, datetime.now(timezone.utc), evidence_root)
    assert "Actual target deployment evidence is required" in errors


def test_short_pilot_cannot_satisfy_observation_period(evidence_root):
    now = datetime.now(timezone.utc)
    report = {"environment": "deployed", "api_url": "https://api.mdt.invalid", "started_at": now.isoformat(),
              "ended_at": now.isoformat(), "external_users": 10, "open_high_critical": 0}
    policy = json.loads((evidence_root / "readiness-policy.json").read_text())
    errors = gate.gate_errors("pilot", report, policy, report, now, evidence_root)
    assert "Pilot observation period is incomplete" in errors


@pytest.mark.parametrize("fault", [None, "alter-label", "omit-family", "tuning-corpus", "duplicate-case", "fake-summary"])
def test_accuracy_gate_recomputes_results_from_frozen_labels(evidence_root, fault):
    # Explicitly reduced thresholds for gate logic only, not release evidence.
    policy = json.loads((evidence_root / "readiness-policy.json").read_text())
    policy["accuracy"].update(min_positive_cases_per_family=1, min_negative_cases_per_family=1,
                              min_holdout_repositories=1)
    now = datetime.now(timezone.utc)
    repository = "example-fixture/unseen" if fault != "tuning-corpus" else "fastapi/fastapi"
    provenance = {"independent": True, "reviewers": ["fixture-a", "fixture-b"], "adjudicated": True,
                  "frozen_at": (now - timedelta(days=1)).isoformat(), "used_for_tuning": False,
                  "repository_revisions": {repository: "a" * 40}}
    originals = [{"id": f"{family}-{label}", "family": family, "expected": label, "repository": repository}
                 for family in policy["accuracy"]["families"] for label in (True, False)]
    if fault == "omit-family":
        originals = originals[2:]
    path = evidence_root / "holdout.json"
    path.write_text(json.dumps({"split": "holdout", "provenance": provenance, "cases": originals}))
    cases = [{"id": c["id"], "family": c["family"], "expected": c["expected"], "predicted": c["expected"]}
             for c in originals]
    if fault == "alter-label":
        cases[0]["expected"] = not cases[0]["expected"]
    if fault == "duplicate-case":
        cases[0] = cases[1]
    if fault == "fake-summary":
        cases[0]["predicted"] = None
    report = {"split": "holdout", "provenance": provenance, "cases": cases,
              "dataset": {"path": path.name, "sha256": digest_file(path)}, "dataset_sha256": digest_file(path),
              "created_at": now.isoformat(), "meets_statistical_targets": True}
    errors = gate.gate_errors("accuracy", report, policy, {}, now, evidence_root)
    assert bool(errors) == (fault is not None)


def test_source_identity_changes_when_uncommitted_code_changes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import readiness_common as common
    path = tmp_path / "backend/service.py"
    path.parent.mkdir()
    path.write_text("x = 1\n")
    def listed(args, **kwargs):
        assert "--others" in args and "--cached" in args
        return SimpleNamespace(stdout=b"backend/service.py\0")
    monkeypatch.setattr(common.subprocess, "run", listed)
    before = common.source_identity(tmp_path)
    path.write_text("x = 2\n")
    after = common.source_identity(tmp_path)
    assert before["sha256"] != after["sha256"]
