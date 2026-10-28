"""Keep measured static scope separate from unobserved runtime communication."""

RUNTIME_CAVEATS = {
    "static_topology_is_not_complete_runtime_communication",
    "compose_dependencies_are_startup_order_not_verified_calls",
    "compose_uses_recorded_defaults_not_runtime_environment",
}


def _count(value):
    # Missing historical measurements are unknown, never invented zeroes.
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def coverage_indicators(coverage):
    """Derive displayable dimensions from recorded measurements, including old captures.

    Complete source scanning describes eligible *mapped* files only. It does not
    claim all repository files, resolved contracts, or observed runtime behavior.
    """
    coverage = coverage if isinstance(coverage, dict) else {}
    eligible = _count(coverage.get("candidate_files", coverage.get("files_candidates")))
    read = _count(coverage.get("files_read"))
    attempted = _count(coverage.get("files_attempted"))
    omitted = max(0, eligible - read) if eligible is not None and read is not None else None
    scan_reasons = []
    inconsistent_scan = (eligible is not None and read is not None and read > eligible
                         or attempted is not None and read is not None and attempted < read
                         or attempted is not None and eligible is not None and attempted > eligible
                         or "files_attempted" in coverage and attempted is None)
    if inconsistent_scan:
        scan_status = "unavailable"
        scan_reasons.append("source_scan_counts_inconsistent")
    elif eligible is None or read is None:
        scan_status = "unavailable"
        scan_reasons.append("source_scan_counts_unavailable")
    elif eligible == 0:
        scan_status = "unavailable"
        scan_reasons.append("no_eligible_mapped_source")
    else:
        scan_status = "complete" if read == eligible else "partial"
        if omitted:
            scan_reasons.append("eligible_source_not_read")
    scan_reasons.extend(coverage.get("scan_reason_counts", {}))
    parsers = coverage.get("parsers")
    parsed = heuristic = failed = partial = unclassified = None
    parser_reasons = []
    parser_counts_recorded = (isinstance(parsers, dict) and bool(parsers)
                              or isinstance(parsers, dict) and read == 0
                              and coverage.get("coverage_schema_version") == 2)
    parser_counts_valid = (parser_counts_recorded
                          and all(_count(value) is not None for value in parsers.values()))
    if parser_counts_valid and read is not None:
        parsed = sum(_count(parsers.get(name)) or 0 for name in ("ast", "tree_sitter"))
        heuristic, failed, partial = (_count(parsers.get(name)) or 0 for name in ("heuristic", "failed", "partial"))
        unclassified = max(0, read - parsed - heuristic - failed - partial)
        parser_status = "supported" if read > 0 and parsed == read else "partial" if read > 0 else "unavailable"
        if sum(parsers.values()) > read:
            parser_status = "unavailable"
            parser_reasons.append("parser_counts_inconsistent")
        if heuristic:
            parser_reasons.append("heuristic_languages_not_semantically_parsed")
        if failed:
            parser_reasons.append("source_parse_failures")
        if partial:
            parser_reasons.append("parser_limits_reached")
        if unclassified:
            parser_reasons.append("parser_outcomes_unavailable")
        if not read:
            parser_reasons.append("no_source_read")
    else:
        parser_status = "unavailable"
        parser_reasons.append("parser_counts_inconsistent" if parser_counts_recorded and not parser_counts_valid
                              else "parser_counts_unavailable")
    unsupported = coverage.get("unsupported_contract_services", [])
    if unsupported:
        parser_reasons.append("service_contract_extraction_unsupported")
        if parser_status == "supported":
            parser_status = "partial"
    runtime_known_static = (coverage.get("source") == "static_source"
                            or bool(RUNTIME_CAVEATS.intersection(coverage.get("warnings", []))))
    return {
        "source_scan": {
            "status": scan_status, "scope": "eligible_mapped_source_files",
            "eligible_files": eligible, "read_files": read, "attempted_files": attempted,
            "omitted_files": omitted, "excluded_source_files": _count(coverage.get("excluded_source_files")),
            "unmapped_source_files": _count(coverage.get("unmapped_source_files")),
            "bytes_read": _count(coverage.get("bytes_read")), "limits": coverage.get("scan_limits", {}),
            "missing_source_services": coverage.get("missing_source_services", []),
            "external_source_services": coverage.get("external_source_services", []),
            "reason_counts": coverage.get("scan_reason_counts", {}), "reasons": sorted(set(scan_reasons)),
        },
        "parser_support": {
            "status": parser_status, "scope": "syntax_parsing_of_read_source",
            "parsed_files": parsed, "read_files": read, "heuristic_files": heuristic,
            "failed_files": failed, "partial_files": partial, "unclassified_files": unclassified,
            "unsupported_contract_services": unsupported, "reasons": parser_reasons,
        },
        "runtime_verification": {
            "status": "not_measured" if runtime_known_static else "unavailable",
            "reasons": ["runtime_traffic_not_measured" if runtime_known_static else "runtime_measurement_unavailable"],
        },
    }


def static_coverage_reasons(coverage):
    """Only static gaps qualify static evidence; runtime has its own indicator."""
    if not isinstance(coverage, dict) or not coverage:
        return ["topology_source_coverage_unavailable"]
    dimensions = coverage_indicators(coverage)
    reasons = []
    if dimensions["source_scan"]["status"] != "complete":
        reasons.append("topology_source_scan_incomplete")
    if dimensions["parser_support"]["status"] != "supported":
        reasons.append("topology_parser_support_incomplete")
    if coverage.get("missing_source_services") or coverage.get("external_source_services"):
        reasons.append("declared_service_source_unavailable")
    if any(warning not in RUNTIME_CAVEATS for warning in coverage.get("warnings", [])):
        reasons.append("topology_static_evidence_limitations")
    return reasons
