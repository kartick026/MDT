// Source extraction, syntax support, and runtime observation describe different scopes.
const count = value => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
const firstCount = (...values) => values.map(count).find(value => value !== null) ?? null;
const listSize = value => Array.isArray(value) ? value.length : null;
const hasTopologyCounts = coverage => coverage && ['indicators', 'candidate_files', 'files_candidates', 'parsers', 'per_service_candidates'].some(key => Object.hasOwn(coverage, key));

export function topologyCoverage(result = {}) {
  return result.topology_coverage || result.evidence?.topology_coverage || result.snapshot?.coverage
    || (hasTopologyCounts(result.coverage) ? result.coverage : null)
    || (hasTopologyCounts(result.evidence?.coverage) ? result.evidence.coverage : null) || {};
}

export function coverageIndicators(result = {}) {
  const coverage = topologyCoverage(result);
  const indicators = coverage.indicators || {};
  const scan = indicators.source_scan || {};
  const parser = indicators.parser_support || {};
  const runtime = indicators.runtime_verification || {};
  const legacy = !coverage.indicators && Object.keys(coverage).length > 0;
  const illustrative = result.status === 'demo' || result.evidence?.mode === 'illustrative_demo' || result.provenance?.source === 'illustrative_demo';
  const eligible = firstCount(scan.eligible_files, coverage.candidate_files, coverage.files_candidates);
  const read = firstCount(scan.read_files, coverage.files_read);
  const attempted = firstCount(scan.attempted_files, coverage.files_attempted);
  const parserRead = firstCount(parser.read_files, read);
  const modes = coverage.parsers;
  const hasModes = modes && typeof modes === 'object' && Object.keys(modes).length > 0;
  const modeCount = key => hasModes ? count(modes[key] ?? 0) : null;
  const parsed = firstCount(parser.parsed_files, hasModes ? (modeCount('ast') ?? 0) + (modeCount('tree_sitter') ?? 0) : null);
  const heuristic = firstCount(parser.heuristic_files, modeCount('heuristic'));
  const failed = firstCount(parser.failed_files, modeCount('failed'));
  const partial = firstCount(parser.partial_files, modeCount('partial'));
  const unclassified = firstCount(parser.unclassified_files, parserRead !== null && parsed !== null
    ? Math.max(0, parserRead - parsed - (heuristic ?? 0) - (failed ?? 0) - (partial ?? 0)) : null);
  const sourceInconsistent = (eligible !== null && read !== null && read > eligible) || (attempted !== null && read !== null && attempted < read)
    || (attempted !== null && eligible !== null && attempted > eligible) || scan.reasons?.includes('source_scan_counts_inconsistent');
  const parserInconsistent = parser.reasons?.includes('parser_counts_inconsistent') || (hasModes && Object.values(modes).some(value => count(value) === null))
    || (parserRead !== null && ((read !== null && parserRead !== read)
    || [parsed, heuristic, failed, partial, count(parser.unclassified_files)].reduce((sum, value) => sum + (value ?? 0), 0) > parserRead));
  const sourceStatus = sourceInconsistent || scan.status === 'unavailable' || eligible === null || read === null || !eligible ? 'unavailable'
    : read < eligible || scan.status === 'partial' ? 'partial' : 'complete';
  const unsupported = listSize(parser.unsupported_contract_services ?? coverage.unsupported_contract_services);
  const parserStatus = parserInconsistent || parser.status === 'unavailable' || parsed === null || !parserRead ? 'unavailable'
    : parsed < parserRead || parser.status === 'partial' || unsupported ? 'partial' : 'supported';
  const sourceValue = eligible !== null && read !== null ? `${read} / ${eligible} eligible files read` : 'Not recorded';
  const sourceNotes = ['Eligible files are supported source paths mapped to discovered services; this is not all repository files.'];
  if (sourceInconsistent) sourceNotes.push('Recorded scan counters are inconsistent; completeness cannot be established.');
  if (attempted !== null) sourceNotes.push(`${attempted} file reads attempted.`);
  for (const [value, label] of [
    [count(scan.omitted_files), 'eligible files omitted'], [count(scan.unmapped_source_files), 'source files outside discovered service mappings'],
    [count(scan.excluded_source_files), 'source files excluded by scan policy'],
    [listSize(scan.missing_source_services ?? coverage.missing_source_services), 'services with mapped source not read'],
    [listSize(scan.external_source_services ?? coverage.external_source_services), 'declared services without captured source'],
  ]) if (value) sourceNotes.push(`${value} ${label}.`);
  if (legacy) sourceNotes.push('Derived from recorded counts in this saved snapshot. Re-import to apply scanner updates.');
  if (illustrative) sourceNotes.push('Illustrative demo topology; no repository-wide source scan is claimed.');
  const parserNotes = ['Syntax-parsed files count AST and Tree-sitter results. Language and contract support can still be incomplete.'];
  if (parserInconsistent) parserNotes.push('Recorded parser counters are inconsistent; parser completeness cannot be established.');
  if (heuristic !== null) parserNotes.push(`${heuristic} heuristic · ${failed ?? 'unknown'} failed · ${partial ?? 'unknown'} partial · ${unclassified ?? 'unknown'} unclassified.`);
  if (unsupported) parserNotes.push(`${unsupported} services lack supported contract extraction.`);
  const measured = result.architecture_health?.evidence?.runtime_traffic_measured;
  const runtimeStatus = runtime.status || (measured === false || coverage.source === 'static_source' || illustrative ? 'not_measured' : 'unavailable');
  return [
    { key: 'source_scan', title: 'Source scan', status: sourceStatus, label: sourceInconsistent ? 'Inconsistent counts' : sourceStatus === 'complete' ? 'Eligible scope read' : sourceStatus === 'partial' ? 'Incomplete scan' : eligible === 0 ? 'No eligible files' : 'Not recorded', value: sourceValue, notes: sourceNotes, recorded: legacy },
    { key: 'parser_support', title: 'Parser support', status: parserStatus, label: parserInconsistent ? 'Inconsistent counts' : parserStatus === 'supported' ? 'Syntax parsed' : parserStatus === 'partial' ? 'Mixed parser support' : parserRead === 0 ? 'No source read' : 'Not recorded', value: parsed !== null && parserRead !== null ? `${parsed} / ${parserRead} read files syntax parsed` : 'Not recorded', notes: parserNotes, recorded: legacy },
    { key: 'runtime_verification', title: 'Runtime verification', status: runtimeStatus, label: runtimeStatus === 'not_measured' ? 'Not measured' : 'Not recorded', value: runtimeStatus === 'not_measured' ? 'Traffic not observed' : 'No runtime measurement supplied', notes: ['Static dependencies and configuration do not establish actual runtime communication.'], recorded: legacy },
  ];
}
