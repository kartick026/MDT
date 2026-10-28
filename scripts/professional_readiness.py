"""Fail-closed evidence checks for a professional release candidate.

Evidence hashes detect accidental substitution, not dishonest attestations.
Human reviewers must inspect the referenced records before release approval.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.readiness_common import ROOT, digest_file, source_identity, write_report, utc_now
from scripts.evaluate_accuracy import summarize
from scripts.release_preflight import check as check_metadata


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a timezone")
    return parsed


def number(value):
    return type(value) in (float, int) and math.isfinite(value)


def named_checks(report, names):
    checks = report.get("checks", [])
    return isinstance(checks, list) and all(any(isinstance(c, dict) and c.get("name") == name
        and c.get("passed") is True for c in checks) for name in names)


def safe_artifact(root, entry):
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise ValueError("Evidence requires a relative path and SHA-256")
    path = Path(entry["path"])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Evidence path must stay inside this checkout")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Missing or out-of-checkout evidence file")
    if digest_file(resolved) != entry.get("sha256"):
        raise ValueError("Evidence digest mismatch")
    return resolved


def gate_errors(gate, report, policy, config, now, root):
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)

    if gate == "accuracy":
        need(report.get("split") == "holdout", "Development controls cannot certify accuracy")
        provenance = report.get("provenance", {})
        reviewers = provenance.get("reviewers", [])
        need(provenance.get("independent") is True and len(set(reviewers)) >= 2,
             "Two independent human label reviewers and adjudication are required")
        need(provenance.get("adjudicated") is True, "Unresolved labels require adjudication")
        dataset = safe_artifact(root, report["dataset"])
        need(digest_file(dataset) == report.get("dataset_sha256"), "Dataset identity differs from evaluation")
        data = json.loads(dataset.read_text(encoding="utf-8-sig"))
        need(data.get("split") == "holdout" and data.get("provenance") == provenance,
             "Dataset split and provenance must match the report")
        frozen = timestamp(provenance["frozen_at"])
        need(frozen <= timestamp(report["created_at"]), "Holdout must be frozen before evaluation")
        need(provenance.get("used_for_tuning") is False, "A tuning corpus cannot serve as a holdout")
        repositories = provenance.get("repository_revisions", {})
        tuning = json.loads((root / "evaluation/tuning-repositories.json").read_text())["repositories"]
        need(not ({name.casefold() for name in repositories} & {name.casefold() for name in tuning}),
             "Repositories previously used for tuning are not eligible holdouts")
        need(len(repositories) >= policy["accuracy"]["min_holdout_repositories"]
             and all(isinstance(v, str) and len(v) == 40 and all(c in "0123456789abcdef" for c in v) for v in repositories.values()),
             "Insufficient pinned holdout repositories")
        cases, originals = report["cases"], data["cases"]
        labels = {c["id"]: (c["family"], c["expected"]) for c in originals}
        need(len(cases) == len(originals) == len(labels) == len({c["id"] for c in cases}), "Missing or duplicated cases")
        need(all(labels.get(c["id"]) == (c["family"], c["expected"]) for c in cases), "Evaluation labels changed")
        need(all(c.get("repository") in repositories for c in originals), "Every holdout case needs repository provenance")
        for c in cases:
            if c["family"] not in policy["accuracy"]["families"] or type(c["expected"]) is not bool or (c["predicted"] is not None and type(c["predicted"]) is not bool):
                raise ValueError("Invalid or unadjudicated holdout case")
        metrics = summarize(cases, policy["accuracy"]["families"], policy["accuracy"])
        need(all(m["meets_targets"] for m in metrics.values()), "Accuracy, coverage or sample-size targets failed")
    elif gate == "security":
        need(report.get("review_type") == "independent" and bool(report.get("reviewer")), "Independent application review is required")
        need(type(report.get("open_high_critical")) is int and report["open_high_critical"] == 0, "Unresolved high/critical findings")
        need(named_checks(report, ("account-isolation", "source-upload", "untrusted-repository", "credentials",
                                   "deletion", "abuse", "dependency-scan")), "Security scenarios are incomplete")
    elif gate in {"operations", "clients", "pilot"}:
        need(report.get("environment") == "deployed" and report.get("api_url") == config.get("api_url"),
             "Actual target deployment evidence is required")
        if gate == "operations":
            targets = policy["operations"]
            limits = {"concurrency": (targets["pilot_concurrency"] * targets["test_concurrency_multiplier"], None),
                      "request_count": (targets["pilot_concurrency"] * targets["test_concurrency_multiplier"] * 100, None),
                      "duration_seconds": (600, None), "success_rate": (targets["min_success_rate"], 1),
                      "api_p95_ms": (0, targets["max_api_p95_ms"]), "restore_seconds": (0, targets["max_restore_seconds"]),
                      "data_loss_seconds": (0, targets["max_data_loss_seconds"])}
            for field, (low, high) in limits.items():
                value = report.get(field)
                need(number(value) and value >= low and (high is None or value <= high), field + " target not met")
            need(named_checks(report, ("worker-crash", "database-outage", "queue-saturation", "backup-restore",
                 "rollback", "https-cors", "alerts")), "Deployment recovery scenarios are incomplete")
        elif gate == "clients":
            runs = report.get("runs", [])
            for client in policy["clients"]:
                matching = [r for r in runs if r.get("client") == client and r.get("passed") is True
                            and r.get("version") and r.get("os") and r.get("parity_verified") is True]
                need(bool(matching), client + " needs deployed acceptance and result parity")
                if client == "vscode_desktop":
                    need(len({r["os"] for r in matching}) >= 2, "Desktop extension requires two operating systems")
            need(named_checks(report, ("grant-denial", "token-revocation", "upload-cancel-send", "restricted-mode")),
                 "Native permission and credential scenarios are incomplete")
        else:
            start, end = timestamp(report["started_at"]), timestamp(report["ended_at"])
            need(start <= end <= now and (end - start).total_seconds() >= policy["pilot"]["min_days"] * 86400,
                 "Pilot observation period is incomplete")
            need(type(report.get("external_users")) is int and report["external_users"] >= policy["pilot"]["min_external_users"],
                 "Too few external pilot users")
            need(type(report.get("open_high_critical")) is int and report["open_high_critical"] == 0, "Pilot has unresolved major defects")
            need(named_checks(report, ("finding-review", "support-response", "incident-review")), "Pilot review records are missing")
    elif gate == "approval":
        need(bool(report.get("reviewer")) and report.get("approved") is True, "Maintainer release approval is missing")
        need(named_checks(report, ("license", "privacy", "support", "scope", "rollback-owner")), "Release ownership decisions are missing")
        artifacts = report.get("artifacts", {})
        for client in ("web", "browser", "vscode"):
            safe_artifact(root, artifacts[client])
    return errors


def check_professional(manifest, config, root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    policy = json.loads((root / "readiness-policy.json").read_text(encoding="utf-8"))
    identity = source_identity(root)
    results = []
    entries = manifest.get("evidence", {})
    for gate in policy["required_evidence"]:
        errors = []
        try:
            if manifest.get("schema_version") != 1 or gate not in entries:
                raise ValueError("Required evidence is missing")
            path = safe_artifact(root, entries[gate])
            report = json.loads(path.read_text(encoding="utf-8-sig"))
            if report.get("schema_version") != 1 or report.get("kind") != gate or report.get("status") != "passed":
                errors.append("Evidence is incomplete, failed or has the wrong scope")
            if report.get("source", {}).get("sha256") != identity["sha256"]:
                errors.append("Evidence does not match the current source")
            age = (now - timestamp(report["created_at"])).total_seconds()
            if age < -300 or age > policy["max_evidence_age_days"] * 86400:
                errors.append("Evidence is stale or dated in the future")
            errors.extend(gate_errors(gate, report, policy, config, now, root))
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
            errors.append("Invalid evidence: " + str(error))
        results.append({"gate": gate, "passed": not errors, "remaining": errors})
    metadata_remaining = check_metadata(config)
    return {"professional_ready": not metadata_remaining and all(r["passed"] for r in results), "source": identity,
            "metadata_remaining": metadata_remaining,
            "checked_at": utc_now(), "gates": results,
            "scope": "Recorded evidence validation; not independent certification or permission to publish"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "release-evidence.example.json")
    parser.add_argument("--config", type=Path, default=ROOT / "release-config.example.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_professional(json.loads(args.manifest.read_text(encoding="utf-8-sig")),
                                json.loads(args.config.read_text(encoding="utf-8-sig")))
    if args.output:
        write_report(args.output, result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["professional_ready"] else 2)
