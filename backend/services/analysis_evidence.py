"""Observable analysis coverage. These ratios are not predictive confidence."""
from services.dependency_graph import _infer_service_from_path
from services.coverage_indicators import coverage_indicators, static_coverage_reasons


def assess_evidence(changes, snapshot):
    total = len(changes)
    effective = [c for c in changes if c.ast_metadata.get("semantic_change") is not False]
    complete = sum(c.extraction_status == "complete" for c in changes)
    understood = sum(c.ast_metadata.get("semantic_change") is not None for c in changes)
    mapped = sum(bool(_infer_service_from_path(c.file_path)
                      or _infer_service_from_path(c.previous_path or "")) for c in effective)
    coverage = snapshot.get("coverage", {})
    reasons = []
    if complete < total:
        reasons.append("changed_source_incomplete")
    if understood < total:
        reasons.append("semantic_comparison_unavailable")
    if mapped < len(effective):
        reasons.append("changed_files_not_mapped_to_services")
    candidates = coverage.get("per_service_candidates", {})
    reads = coverage.get("per_service_parsed", coverage.get("per_service", {}))
    unresolved = sorted({name for c in effective for name in
                         c.ast_metadata.get("contract_changes", {}).get("unresolved_models", [])})
    if unresolved:
        reasons.append("imported_contract_models_unresolved")
    services = {_infer_service_from_path(c.file_path) or _infer_service_from_path(c.previous_path or "")
                for c in effective}
    service_ratios = {}
    for name in sorted(services - {None, ""}):
        count = candidates.get(name, 0)
        service_ratios[name] = min(1.0, reads.get(name, 0) / count) if count else 0.0
    if effective and not coverage:
        reasons.append("topology_source_coverage_unavailable")
    elif any(value < 1 for value in service_ratios.values()):
        reasons.append("affected_service_source_coverage_incomplete")
    if coverage.get("coverage_schema_version", 0) >= 2:
        reasons.extend(static_coverage_reasons(coverage))
    elif coverage.get("partial") or coverage.get("warnings"):
        # Historical captures lack the dimensions needed to separate the old
        # umbrella flag safely. Preserve their recorded uncertainty.
        reasons.append("topology_coverage_partial")
    source_ratio = min(complete, understood) / total if total else 0.0
    mapping_ratio = mapped / len(effective) if effective else 1.0
    topology_ratio = min(service_ratios.values(), default=0.0) if effective else 1.0
    # Report the weakest observable evidence dimension, not an invented probability.
    value = round(min(source_ratio, mapping_ratio, topology_ratio), 3)
    if not changes:
        status = "no_changes"
    elif not effective:
        status = "no_semantic_change"
    elif value == 0:
        status = "insufficient_evidence"
    elif reasons:
        status = "partial"
    else:
        status = "supported"
    return value, status, {
        "kind": "evidence_completeness", "calibrated": False,
        "interpretation": "Coverage of available static evidence, not probability of correctness or deployment success",
        "changed_files": total, "effective_changed_files": len(effective),
        "equivalent_files": total - len(effective), "complete_source_files": complete,
        "semantically_compared_files": understood, "mapped_effective_files": mapped,
        "affected_service_source_ratios": service_ratios,
        "unresolved_contract_models": unresolved,
        "topology_indicators": coverage_indicators(coverage),
        "reasons": reasons,
    }
