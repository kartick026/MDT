"""Evaluate labeled source pairs without executing repository code or using a network.

Development controls are regression evidence only. A professional gate requires
a separately frozen, human-adjudicated holdout; this tool never invents labels.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.readiness_common import ROOT, digest_file, evidence, write_report


def wilson(successes, total):
    if not total:
        return None
    z, p = 1.959963984540054, successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def summarize(rows, families, targets):
    metrics = {}
    for family in families:
        selected = [r for r in rows if r["family"] == family]
        labeled = [r for r in selected if type(r["expected"]) is bool]
        tp = sum(r["expected"] is True and r["predicted"] is True for r in labeled)
        fp = sum(r["expected"] is False and r["predicted"] is True for r in labeled)
        fn = sum(r["expected"] is True and r["predicted"] is False for r in labeled)
        tn = sum(r["expected"] is False and r["predicted"] is False for r in labeled)
        positives = sum(r["expected"] is True for r in labeled)
        negatives = len(labeled) - positives
        abstained = sum(r["predicted"] is None for r in labeled)
        abstained_positive = sum(r["expected"] is True and r["predicted"] is None for r in labeled)
        precision = tp / (tp + fp) if tp + fp else None
        # Abstaining on a known positive still misses that finding.
        recall = tp / positives if positives else None
        coverage = (len(labeled) - abstained) / len(labeled) if labeled else None
        metrics[family] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "positives": positives,
            "negatives": negatives, "abstained": abstained, "abstained_positive": abstained_positive,
            "unlabeled": len(selected) - len(labeled), "precision": precision, "recall": recall,
            "prediction_coverage": coverage, "precision_interval_95": wilson(tp, tp + fp),
            "recall_interval_95": wilson(tp, positives),
            "meets_targets": all((
                precision is not None and precision >= targets["min_precision"],
                recall is not None and recall >= targets["min_recall"],
                coverage is not None and coverage >= targets["min_prediction_coverage"],
                positives >= targets["min_positive_cases_per_family"],
                negatives >= targets["min_negative_cases_per_family"],
            )),
        }
    return metrics


def predict(case):
    os.environ.setdefault("TESTING", "true")
    sys.path.insert(0, str(ROOT / "backend"))
    from services.git_analyzer import GitAnalyzer
    from services.impact_engine import ImpactEngine

    changes = GitAnalyzer().analyze_local_changes(case["changes"], base_sha="a" * 40,
        commit_sha="b" * 40, source_context=case.get("source_context"))
    if not changes or any(c.extraction_status == "partial" or c.ast_metadata.get("semantic_change") is None for c in changes):
        return None
    engine = ImpactEngine()
    family = case["family"]
    if family == "semantic_change":
        return any(c.ast_metadata["semantic_change"] for c in changes)
    if family == "breaking_route":
        if any(c.ast_metadata.get("contract_changes", {}).get("compatibility") == "uncertain" for c in changes):
            return None
        return engine._has_breaking_api_changes(changes)
    if family == "schema_change":
        if any(not c.file_path.endswith(".py") for c in changes):
            return None
        return engine._has_schema_changes(changes)
    if family == "deployment_change":
        return engine._has_config_changes(changes)
    raise ValueError("Unsupported finding family: " + family)


def evaluate(dataset, targets, predictor=predict):
    if dataset.get("schema_version") != 1 or dataset.get("split") not in {"development", "holdout"}:
        raise ValueError("A versioned development or holdout dataset is required")
    cases = dataset.get("cases", [])
    if not cases:
        raise ValueError("No labeled cases; an empty dataset cannot pass")
    seen, rows = set(), []
    for case in cases:
        ident = case.get("id")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError("Case IDs must be nonempty and unique")
        seen.add(ident)
        if case.get("family") not in targets["families"]:
            raise ValueError("Unknown finding family")
        if "expected" not in case or (case["expected"] is not None and type(case["expected"]) is not bool):
            raise ValueError("Expected labels must be true, false or null (unknown)")
        if not isinstance(case.get("changes"), list) or not case["changes"]:
            raise ValueError("Each case requires source changes")
        predicted = predictor(case)
        if predicted is not None and type(predicted) is not bool:
            raise ValueError("Predictor must return true, false or abstain")
        rows.append({"id": ident, "family": case["family"], "expected": case["expected"],
                     "predicted": predicted, "matches_control": predicted is case["expected"]})
    metrics = summarize(rows, targets["families"], targets)
    return {"split": dataset["split"], "provenance": dataset.get("provenance", {}),
            "case_count": len(rows), "metrics": metrics, "cases": rows,
            "controls_passed": all(row["matches_control"] for row in rows),
            "meets_statistical_targets": all(m["meets_targets"] for m in metrics.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/development.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    targets = json.loads((ROOT / "readiness-policy.json").read_text())["accuracy"]
    dataset = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    result = evaluate(dataset, targets)
    passed = result["controls_passed"] if result["split"] == "development" else result["meets_statistical_targets"]
    dataset_path = args.dataset.resolve().relative_to(ROOT).as_posix()
    report = evidence("accuracy", status="passed" if passed else "failed", dataset_sha256=digest_file(args.dataset),
        dataset={"path": dataset_path, "sha256": digest_file(args.dataset)},
        scope="Offline static analysis; no repository execution; risk scores are not calibrated probabilities", **result)
    write_report(args.output, report)
    print(json.dumps({"status": report["status"], "cases": result["case_count"], "split": result["split"],
                      "meets_statistical_targets": result["meets_statistical_targets"], "output": str(args.output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
