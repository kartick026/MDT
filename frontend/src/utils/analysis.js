export function numericScore(value) {
  if (!['number', 'string'].includes(typeof value) || (typeof value === 'string' && !value.trim())) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function formatScore(value) {
  const numeric = numericScore(value);
  return numeric !== null
    ? numeric.toFixed(3).replace(/\.?0+$/, '')
    : 'Unavailable';
}

export function architectureSummary(result = {}) {
  const health = result.architecture_health || {};
  const score = numericScore(result.architecture_smell_score ?? health.score);
  const status = health.assessment_status || 'unknown';
  const insufficient = status === 'insufficient_communication_evidence';
  const partial = insufficient || status === 'partial' || result.partial_results === true || result.coverage?.status === 'partial' || result.coverage?.partial === true;
  const severity = String(health.severity || '').toUpperCase();
  const label = score === null ? 'Architectural debt unavailable' : insufficient ? 'Insufficient communication evidence'
    : partial ? 'Partial architecture assessment' : ['HIGH', 'CRITICAL'].includes(severity) ? 'High Recorded Debt'
    : severity === 'MEDIUM' ? 'Moderate Recorded Debt' : severity === 'LOW' ? 'Low Recorded Debt' : 'Recorded Architectural Debt';
  return { score, status, partial, insufficient, label,
    tone: score === null || partial || !severity ? 'neutral' : ['HIGH', 'CRITICAL'].includes(severity) ? 'danger' : severity === 'MEDIUM' ? 'warning' : 'success',
    interpretation: health.interpretation || 'Recorded findings only; zero does not establish a debt-free or safe architecture.',
    evidence: health.evidence || {}, detectorVersion: health.detector_version || result.evidence?.detector_version,
  };
}

export function jobResult(job) {
  if (!job?.result) return null;
  const result = job.result.analysis || job.result;
  return { ...result, analysis_id: result.analysis_id || job.id || job.job_id,
    project_id: result.project_id || job.project, repo_url: result.repo_url || result.project?.repo_url };
}

export function scoreDelta(before, after) {
  if (before == null || after == null || before === '' || after === '') return null;
  const first = Number(before), second = Number(after);
  return Number.isFinite(first) && Number.isFinite(second) ? second - first : null;
}

export function graphEditLabel(edit) {
  if (edit.action === 'remove_edge' || edit.action === 'add_edge') return `${edit.action === 'remove_edge' ? '−' : '+'} Edge: ${edit.from_service} → ${edit.to_service}`;
  if (edit.action === 'update_node') return `✎ Node: ${edit.from_service} (hypothetical resilience)`;
  if (edit.action === 'add_node') return `+ Node: ${edit.from_service}`;
  return edit.action;
}

export function previewChange(preview) {
  const value = preview?.delta?.score_reduction;
  const reduction = Number(value);
  if (value == null || !Number.isFinite(reduction)) return { text: 'Unavailable', label: 'No measured score change', improved: false };
  return { text: `${reduction > 0 ? '−' : reduction < 0 ? '+' : ''}${formatScore(Math.abs(reduction))} pts`,
    label: reduction > 0 ? 'Lower recorded debt' : reduction < 0 ? 'Higher recorded debt' : 'Debt unchanged', improved: reduction > 0 };
}

export function evidenceSummary(result = {}) {
  const evidence = result.evidence || result.provenance || {};
  const coverage = result.coverage || evidence.coverage || {};
  const warnings = [...new Set([
    ...(Array.isArray(result.warnings) ? result.warnings : []),
    ...(Array.isArray(coverage.warnings) ? coverage.warnings : []),
  ])];
  return {
    mode: evidence.mode || result.analysis_mode || result.mode || 'Evidence mode not supplied',
    parser: coverage.parser || evidence.parser || 'See individual source findings',
    partial: architectureSummary(result).partial || result.status === 'partial' || coverage.partial === true || coverage.status === 'partial' || ['partial', 'insufficient_evidence'].includes(result.assessment_status),
    semantic: evidence.semantic_used === true || result.semantic_used === true,
    warnings,
  };
}

export function analysisExport(result) {
  return JSON.stringify({ export_schema: 'mdt.analysis-export.v1', exported_at: new Date().toISOString(), analysis: result }, null, 2);
}

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const markdownText = value => escapeHtml(value).replace(/([\\`*_{}[\]()#+.!|>~-])/g, '\\$1');

export function readableExport(result, format = 'md') {
  const findings = result.findings || result.architecture_smells || result.smells || [];
  const evidence = evidenceSummary(result);
  const architecture = architectureSummary(result);
  const details = [
    ['Repository', result.repo_url || 'Recorded reference architecture'],
    ['Revision', result.commit_sha || result.head_sha || 'Not supplied'],
    ['Deployment risk', formatScore(result.risk_score)],
    ['Architectural debt', formatScore(result.architecture_smell_score ?? result.architecture_health?.score)],
    ['Architecture assessment', architecture.label], ['Debt interpretation', architecture.interpretation],
    ...(architecture.detectorVersion ? [['Recorded detector version', architecture.detectorVersion]] : []),
    ...(Object.keys(architecture.evidence).length ? [
      ['Startup relations', architecture.evidence.startup_relations ?? 'Not recorded'],
      ['Configuration references', architecture.evidence.configuration_relations ?? 'Not recorded'],
      ['Static or modeled calls', architecture.evidence.static_or_modeled_calls ?? 'Not recorded'],
      ['Runtime traffic measured', architecture.evidence.runtime_traffic_measured === true ? 'Yes' : 'Not established'],
    ] : []),
    ['Evidence mode', evidence.mode], ['Coverage', evidence.partial ? 'Partial' : 'See source evidence'],
    ...(result.confidence_evidence?.kind === 'evidence_completeness' ? [
      ['Static evidence completeness', `${Math.round((result.confidence || 0) * 100)}% (not prediction accuracy)`],
      ['Assessment', String(result.assessment_status || 'unknown').replaceAll('_', ' ')],
    ] : []),
  ];
  if (format === 'html') return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>MDT analysis report</title><style>body{font:16px/1.6 system-ui;max-width:900px;margin:40px auto;padding:0 24px;color:#162333}dt{font-weight:bold}dd{margin:0 0 12px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:12px 0}</style><h1>MDT analysis report</h1><p>Academic alpha. Scores are engineering indicators, not incident probabilities.</p><dl>${details.map(([key,value]) => `<dt>${key}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl><h2>Findings</h2><ul>${findings.map(f => `<li><strong>${escapeHtml(f.type || f.title || 'Finding')}</strong><p>${escapeHtml(f.description || f.message)}</p><p>${escapeHtml((f.services || []).join(', '))}</p></li>`).join('')}</ul><h2>Evidence and warnings</h2><pre>${escapeHtml(JSON.stringify({evidence: result.evidence, coverage: result.coverage, warnings: evidence.warnings}, null, 2))}</pre></html>`;
  return `# MDT analysis report\n\nAcademic alpha. Scores are engineering indicators, not incident probabilities.\n\n${details.map(([key,value]) => `- **${key}:** ${markdownText(value)}`).join('\n')}\n\n## Findings\n\n${findings.map(f => `- **${markdownText(f.type || f.title || 'Finding')}:** ${markdownText(f.description || f.message || '')}\n  Services: ${markdownText((f.services || []).join(', '))}`).join('\n\n')}\n\n## Warnings\n\n${evidence.warnings.map(value => `- ${markdownText(value)}`).join('\n') || 'No additional warnings supplied. Review JSON source evidence for coverage.'}\n`;
}

export function downloadAnalysis(result, format = 'json', documentObject = document) {
  const safeFormat = ['json', 'md', 'html'].includes(format) ? format : 'json';
  const blob = new Blob([safeFormat === 'json' ? analysisExport(result) : readableExport(result, safeFormat)], { type: { json: 'application/json', md: 'text/markdown', html: 'text/html' }[safeFormat] });
  const url = URL.createObjectURL(blob);
  const link = documentObject.createElement('a');
  link.href = url;
  link.download = `mdt-analysis-${String(result.analysis_id || result.job_id || result.commit_sha || 'result').replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 80)}.${safeFormat}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const TABS = new Set(['projects', 'history', 'account']);
export const PROJECT_VIEWS = ['summary', 'analyze', 'graph', 'findings', 'drift'];
const aliases = { workspace: 'projects', overview: 'projects', impact: 'projects', graph: 'projects', smells: 'projects', signin: 'account', auth: 'account' };
const legacyViews = { impact: 'analyze', graph: 'graph', smells: 'findings' };

export function readRoute(hash = '') {
  const [path, query] = hash.replace(/^#\/?/, '').split('?');
  const params = new URLSearchParams(query || '');
  return {
    tab: TABS.has(path) ? path : aliases[path] || 'projects',
    projectId: params.get('project') || '',
    jobId: params.get('job') || '',
    view: PROJECT_VIEWS.includes(params.get('view')) ? params.get('view') : legacyViews[path] || 'summary',
  };
}

export function routeHash(tab, { projectId = '', jobId = '', view = 'summary' } = {}) {
  const params = new URLSearchParams();
  if (projectId) params.set('project', projectId);
  if (jobId) params.set('job', jobId);
  if (PROJECT_VIEWS.includes(view) && view !== 'summary') params.set('view', view);
  return `#/${TABS.has(tab) ? tab : aliases[tab] || 'projects'}${params.size ? `?${params}` : ''}`;
}
