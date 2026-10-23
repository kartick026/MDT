'use strict';
// Plain presentation data keeps server evidence separate from editor interaction.
const number = value => ['number','string'].includes(typeof value) && String(value).trim() && Number.isFinite(Number(value)) ? Number(value).toFixed(3).replace(/\.?0+$/, '') : 'unavailable';
const label = value => String(value ?? 'Unavailable');
const isPartial = result => result.partial_results || ['partial','insufficient_communication_evidence'].includes(result.architecture_health?.assessment_status);

function resultTree(job) {
  if (!job) return [{ label: 'No analysis loaded', description: 'Run Analyze or Refresh Last Analysis', icon: 'info' }];
  const result = job.result;
  if (!result) return [{ label: `Analysis ${label(job.status)}`, description: job.stage || '', tooltip: label(job.error || job.stage || 'Waiting for the server'), icon: job.status === 'failed' ? 'error' : 'sync' }];
  const evidence = result.evidence || {};
  const files = result.affected_files || [];
  const findings = result.smells || result.findings || [];
  const health = result.architecture_health || {};
  return [
    { label: `Commit risk: ${number(result.risk_score)} / 100`, description: result.severity || '', tooltip: result.explanation || 'Engineering indicator; not an incident probability.', icon: 'pulse' },
    { label: `Architectural debt: ${number(result.architecture_smell_score ?? health.score)} / 100`, icon: 'graph', description: (health.assessment_status || 'assessment not recorded').replaceAll('_',' '),
      tooltip: health.interpretation || 'Recorded findings only; zero does not establish a debt-free or safe architecture.' },
    { label: isPartial(result) ? 'Partial evidence — review warnings' : 'Evidence and revisions', icon: isPartial(result) ? 'warning' : 'info', expanded: true, children: [
      { label: `Recorded detector: ${label(health.detector_version || evidence.detector_version)}` },
      { label: `Architecture evidence: ${JSON.stringify(health.evidence || {})}` },
      { label: `Mode: ${label(evidence.mode)}` },
      { label: `Base: ${label(result.base_sha)}` },
      { label: `Head: ${label(result.commit_sha)}` },
      { label: `Snapshot: ${label(result.snapshot_version)}` },
      { label: `Topology source: ${label(evidence.topology_source)}` },
      { label: `Semantic retrieval: ${evidence.semantic_used === true ? 'used' : evidence.semantic_used === false ? 'not used' : 'not supplied'}` },
      ...(result.warnings || []).map(warning => ({ label: label(warning), icon: 'warning' })),
    ] },
    { label: `Architecture findings (${findings.length})`, icon: 'list-unordered', children: findings.map(finding => ({
      label: label(finding.type || finding.title || 'Finding'), description: `${finding.severity || 'unknown'}${finding.suppressed ? ' · suppressed' : ''}`, icon: 'warning',
      tooltip: [finding.description || finding.message, `Services: ${(finding.services || []).join(', ')}`, `Confidence: ${finding.confidence || 'not supplied'}`].filter(Boolean).join('\n'),
      file_path: finding.file_path, line: finding.line, children: [
        { label: finding.description || finding.message || 'Open web result for evidence.' },
        { label: `Services: ${(finding.services || []).join(', ') || 'not supplied'}` },
        { label: `Evidence: ${JSON.stringify(finding.evidence || {})}` },
      ],
    })) },
    { label: `Changed files (${files.length})`, icon: 'files', children: files.map(file => {
      const contracts = file.contract_changes || {};
      return { label: label(file.file_path), description: `${file.change_type || 'changed'} · ${file.parser_coverage || 'parser unknown'}`, icon: 'file-code', file_path: file.file_path,
        children: [
          { label: `Extraction: ${file.extraction_status || 'not supplied'}` },
          ...(file.extraction_warnings || []).map(warning => ({ label: label(warning), icon: 'warning' })),
          ...['added', 'removed', 'modified'].flatMap(kind => (contracts[kind] || []).map(contract => ({ label: `${kind}: ${contract.method || ''} ${contract.path || contract.endpoint || JSON.stringify(contract)}`.trim(), icon: 'symbol-method' }))),
        ],
      };
    }) },
  ];
}

function statusText(job) {
  if (!job) return '$(shield) MDT';
  if (!job.result) return `${['queued', 'running'].includes(job.status) ? '$(sync~spin)' : '$(shield)'} MDT: ${job.status}`;
  return `${isPartial(job.result) ? '$(warning)' : '$(shield)'} MDT: ${number(job.result.risk_score)} / 100`;
}

module.exports = { resultTree, statusText };
