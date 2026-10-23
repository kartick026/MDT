import { useEffect, useMemo, useRef, useState } from 'react';
import { getFindingReviews, previewAnalysis } from '../api';
import { downloadAnalysis, formatScore, routeHash, graphEditLabel, previewChange, architectureSummary } from '../utils/analysis';
import EvidenceSummary from './EvidenceSummary';
import FindingReview from './FindingReview';
import EvidenceDetails from './EvidenceDetails';

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const severityClass = s => {
  const key = String(s || '').toLowerCase();
  if (key === 'critical') return 'severity-critical';
  if (key === 'high') return 'severity-high';
  if (key === 'medium') return 'severity-medium';
  if (key === 'low') return 'severity-low';
  return 'severity-info';
};

/**
 * Reusable Counterfactual Simulation Panel.
 * Appears immediately below the preview edits button in both finding cards and recommendation cards.
 */
function CounterfactualPanel({ previewData, isLoading, error }) {
  if (isLoading) {
    return (
      <div className="inline-counterfactual-container">
        <div className="counterfactual-loading">
          <span className="spinner-sm" />
          <span>Re-evaluating graph topology with proposed counterfactual edits…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="inline-counterfactual-container">
        <div className="form-error inline-error" role="alert">
          {String(error)}
        </div>
      </div>
    );
  }

  if (!previewData) return null;
  const change = previewChange(previewData);

  return (
    <div className="inline-counterfactual-container">
      <div className="counterfactual-panel">
        <div className="counterfactual-header">
          <div className="counterfactual-badge">
            <span className="pulse-dot green" />
            <strong>Counterfactual Architecture Preview</strong>
          </div>
          <span className="counterfactual-mode-tag">Measured snapshot simulation</span>
        </div>

        <div className="counterfactual-scores">
          <div className="counterfactual-score-card before">
            <span className="cf-label">Before Debt</span>
            <span className="cf-val">{formatScore(previewData.before?.score)}</span>
            <small className="cf-sub">Current State</small>
          </div>
          <div className="counterfactual-arrow">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
          </div>
          <div className="counterfactual-score-card after">
            <span className="cf-label">Simulated Debt</span>
            <span className="cf-val">{formatScore(previewData.after?.score)}</span>
            <small className="cf-sub">With Proposed Edits</small>
          </div>
          <div className="counterfactual-score-card reduction">
            <span className="cf-label">Debt Change</span>
            <span className={`cf-val ${change.improved ? 'highlight-green' : ''}`}>
              {change.text}
            </span>
            <small className="cf-sub">{change.label}</small>
          </div>
        </div>

        <p>{previewData.delta?.smells_resolved ?? 0} findings resolved · {previewData.delta?.smells_introduced ?? 0} introduced.</p>
        {!!previewData.warnings?.length && <ul>{previewData.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}

        <p className="counterfactual-disclaimer">
          These scores are recomputed on a copy of the captured topology. No source files are modified. Lower debt does not establish preserved functionality or runtime reliability.
        </p>

        <EvidenceDetails label="Inspect full counterfactual graph payload" value={previewData} />
      </div>
    </div>
  );
}

export default function AnalysisResult({ result, demo = false, view = 'summary' }) {
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const [sortBy, setSortBy] = useState('severity-desc');
  const [format, setFormat] = useState('md');
  const [reviews, setReviews] = useState({});
  const [noticeError, setNoticeError] = useState('');
  const [page, setPage] = useState(0);
  const [expandedId, setExpandedId] = useState(null);
  const [expandAll, setExpandAll] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [copiedMeta, setCopiedMeta] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);

  // Sub-tab view in Findings: 'findings' (all findings) vs 'counterfactual' (recommendations & simulations)
  const [findingsSubView, setFindingsSubView] = useState('findings');

  // Unified counterfactual simulation state keyed by string ID ('rec-0', 'finding-1', etc.)
  const [activeFixKey, setActiveFixKey] = useState(null);
  const [previewMap, setPreviewMap] = useState({});
  const [loadingFixKey, setLoadingFixKey] = useState(null);
  const [fixError, setFixError] = useState('');
  const previewRequest = useRef(null);
  useEffect(() => () => previewRequest.current?.abort(), []);

  const analysisId = result.analysis_id || result.id;
  const PAGE_SIZE = 15;

  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 350);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (demo || view !== 'findings' || !analysisId) return;
    const controller = new AbortController();
    getFindingReviews(analysisId, { signal: controller.signal })
      .then(data => setReviews(Object.fromEntries(data.reviews.map(review => [review.finding_id, review]))))
      .catch(err => { if (!controller.signal.aborted) setNoticeError(`Could not load finding reviews: ${err.message}`); });
    return () => controller.abort();
  }, [demo, view, analysisId]);

  const findings = useMemo(() => result.findings || result.architecture_smells || result.smells || [], [result]);

  // All unique services across findings for dropdown filter
  const allServices = useMemo(() => {
    const set = new Set();
    findings.forEach(f => {
      (f.services || []).forEach(s => set.add(s));
    });
    return [...set].sort();
  }, [findings]);

  // Filter & Search
  const filtered = useMemo(() => {
    return findings
      .filter(finding => {
        if (severity && String(finding.severity).toLowerCase() !== severity) return false;
        if (serviceFilter && !(finding.services || []).includes(serviceFilter)) return false;
        if (query) {
          const q = query.toLowerCase();
          const matchText = (
            (finding.type || finding.title || '') + ' ' +
            (finding.description || finding.message || '') + ' ' +
            (finding.rule || '') + ' ' +
            (finding.category || '') + ' ' +
            (finding.file_path || '') + ' ' +
            (finding.services || []).join(' ')
          ).toLowerCase();
          if (!matchText.includes(q)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'severity-desc') {
          return (SEVERITY_ORDER[String(a.severity).toLowerCase()] ?? 99) - (SEVERITY_ORDER[String(b.severity).toLowerCase()] ?? 99);
        }
        if (sortBy === 'severity-asc') {
          return (SEVERITY_ORDER[String(b.severity).toLowerCase()] ?? 99) - (SEVERITY_ORDER[String(a.severity).toLowerCase()] ?? 99);
        }
        if (sortBy === 'title-asc') {
          return String(a.type || a.title || '').localeCompare(String(b.type || b.title || ''));
        }
        if (sortBy === 'service-asc') {
          const sA = (a.services && a.services[0]) || '';
          const sB = (b.services && b.services[0]) || '';
          return sA.localeCompare(sB);
        }
        return 0;
      });
  }, [findings, severity, serviceFilter, query, sortBy]);

  const severities = useMemo(() =>
    [...new Set(findings.map(f => String(f.severity || '').toLowerCase()).filter(Boolean))]
      .sort((a, b) => (SEVERITY_ORDER[a] ?? 99) - (SEVERITY_ORDER[b] ?? 99)),
    [findings]
  );

  const severityCounts = useMemo(() => {
    const counts = {};
    findings.forEach(f => {
      const s = String(f.severity || 'unknown').toLowerCase();
      counts[s] = (counts[s] || 0) + 1;
    });
    return counts;
  }, [findings]);

  // Recommendations carry structured server evidence, including recorded demo previews.
  const suggestedFixes = useMemo(() => {
    if (result.suggested_fixes && result.suggested_fixes.length > 0) {
      return result.suggested_fixes;
    }

    return [];
  }, [result.suggested_fixes]);

  // Match finding to recommended fix
  const findMatchingFix = finding => {
    const text = ((finding.type || '') + ' ' + (finding.title || '') + ' ' + (finding.rule || '')).toLowerCase();
    const services = finding.services || [];
    return suggestedFixes.find(fix => {
      if (typeof fix === 'string') return false;
      if (fix.finding_ids?.includes(finding.id)) return true;
      if (fix.matchKeywords && fix.matchKeywords.some(kw => text.includes(kw))) {
        if (fix.matchServices && fix.matchServices.length > 0) {
          return fix.matchServices.some(s => services.includes(s));
        }
        return true;
      }
      return false;
    });
  };

  // Simulate counterfactual fix
  const handleTogglePreview = async (fix, key) => {
    if (activeFixKey === key) {
      setActiveFixKey(null);
      return;
    }
    setActiveFixKey(key);
    if (previewMap[key]) return; // already simulated and cached

    setLoadingFixKey(key);
    setFixError('');
    try {
      if (demo) {
        const recorded = fix.recorded_preview;
        if (!recorded || recorded.snapshot_version !== result.snapshot_version || recorded.provenance?.baseline !== 'server_recomputed') {
          throw new Error('No measured preview exists for this recorded snapshot. Refresh the demo.');
        }
        setPreviewMap(prev => ({ ...prev, [key]: recorded }));
      } else {
        previewRequest.current?.abort();
        previewRequest.current = new AbortController();
        const data = await previewAnalysis(analysisId, { edits: fix.edits || [], snapshot_version: result.snapshot_version }, {signal: previewRequest.current.signal});
        setPreviewMap(prev => ({ ...prev, [key]: data }));
      }
    } catch (err) {
      if (err.code !== 'ERR_CANCELED') setFixError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : err.message || 'Counterfactual simulation failed');
    } finally {
      setLoadingFixKey(null);
    }
  };

  const copyFindingMarkdown = async (finding, event) => {
    event?.stopPropagation();
    const id = finding.id || finding.type;
    const md = `### [${String(finding.severity || 'INFO').toUpperCase()}] ${finding.type || finding.title || 'Finding'}\n\n${finding.description || finding.message || ''}\n\n- **Services**: ${(finding.services || []).join(', ') || 'N/A'}\n- **Rule**: ${finding.rule || 'N/A'}\n- **Location**: ${finding.file_path || 'N/A'}${finding.line ? `:${finding.line}` : ''}\n`;
    try {
      await navigator.clipboard.writeText(md);
      setNoticeError('');
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      setNoticeError('Clipboard access was denied. Use Export report to save the evidence.');
    }
  };

  const copyMetaToClipboard = async text => {
    try {
      await navigator.clipboard.writeText(text);
      setNoticeError('');
      setCopiedMeta(true);
      setTimeout(() => setCopiedMeta(false), 2000);
    } catch {
      setNoticeError('Clipboard access was denied. Use Export report to save the evidence.');
    }
  };

  const handleClearAllFilters = () => {
    setQuery('');
    setSeverity('');
    setServiceFilter('');
    setSortBy('severity-desc');
    setPage(0);
  };

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  /* ── Summary View ───────────────────────────────────────────── */
  if (view === 'summary') {
    const architecture = architectureSummary(result);
    const debtScore = architecture.score;
    const riskScore = Number(result.risk_score ?? 0);
    const healthBadge = { label: architecture.label, cls: architecture.tone === 'neutral' ? 'badge-info' : `badge-${architecture.tone}` };

    return (
      <article className="card workspace-result findings-panel">
        {noticeError && <p role="alert" className="form-error">{noticeError}</p>}
        {/* Header */}
        <div className="findings-header">
          <div className="findings-header-text">
            <div className="summary-title-row">
              <h2>{demo ? 'Recorded reference architecture' : result.kind === 'import' ? 'Imported architecture' : 'Analysis summary'}</h2>
              <span className={`badge ${healthBadge.cls}`}>{healthBadge.label}</span>
            </div>
            <div className="summary-meta-row">
              <span className="text-dim">{result.repo_url || 'MDT reference architecture'}</span>
              {result.commit_sha && (
                <button
                  type="button"
                  className="btn-copy-chip"
                  onClick={() => copyMetaToClipboard(result.commit_sha)}
                  title="Copy commit SHA"
                >
                  <code>{result.commit_sha.slice(0, 10)}</code>
                  <span>{copiedMeta ? '✓ Copied' : '📋'}</span>
                </button>
              )}
            </div>
          </div>
          <div className="export-controls">
            <select className="form-select" aria-label="Export format" value={format} onChange={e => setFormat(e.target.value)}>
              <option value="md">Markdown (.md)</option>
              <option value="html">HTML Report</option>
              <option value="json">JSON Data</option>
            </select>
            <button className="btn btn-ghost" onClick={() => downloadAnalysis(result, format)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Export report
            </button>
          </div>
        </div>

        {/* Quick Action Banner */}
        <div className="quick-action-strip">
          <a
            href={routeHash('projects', { projectId: demo ? 'demo' : result.project_id || '', jobId: result.analysis_id || result.id || '', view: 'findings' })}
            className="action-pill primary"
          >
            <span className="action-pill-icon">🔍</span>
            <span className="action-pill-text"><strong>Review {findings.length} Findings</strong></span>
            <span className="action-pill-count">{findings.length}</span>
          </a>
          <a
            href={routeHash('projects', { projectId: demo ? 'demo' : result.project_id || '', jobId: result.analysis_id || result.id || '', view: 'graph' })}
            className="action-pill"
          >
            <span className="action-pill-icon">🕸</span>
            <span className="action-pill-text">Inspect Dependency Topology</span>
          </a>
          {suggestedFixes.length > 0 && (
            <button
              type="button"
              className="action-pill highlight"
              onClick={() => {
                const el = document.getElementById('summary-recommendations');
                el?.scrollIntoView({ behavior: 'smooth' });
              }}
            >
              <span className="action-pill-icon">⚡</span>
              <span className="action-pill-text">Explore {suggestedFixes.length} Counterfactual Previews</span>
              <span className="action-pill-count">{suggestedFixes.length}</span>
            </button>
          )}
          {!demo && (
            <a
              href={routeHash('projects', { projectId: result.project_id || '', view: 'analyze' })}
              className="action-pill"
            >
              <span className="action-pill-icon">⚡</span>
              <span className="action-pill-text">Run Change Analysis</span>
            </a>
          )}
        </div>

        {/* Health Meter & Score cards */}
        <div className="workspace-scores">
          <div className="score-card">
            <span className="score-label">Commit deployment risk</span>
            <strong className={`score-value ${riskScore > 60 ? 'text-orange' : ''}`}>
              {formatScore(result.risk_score)}{result.risk_score != null && '/100'}
            </strong>
            <small>{result.assessment_status === 'insufficient_evidence' ? 'Provisional · Insufficient evidence' : result.assessment_status === 'partial' ? 'Provisional · Partial evidence' : result.severity || 'No commit evaluated'}</small>
          </div>
          <div className="score-card">
            <span className="score-label">Architectural debt</span>
            <strong className={`score-value ${debtScore > 70 ? 'text-red' : ''}`}>
              {formatScore(debtScore)}{debtScore !== null && '/100'}
            </strong>
            <small>{architecture.partial ? 'Provisional · Incomplete static evidence' : 'Heuristic index · Higher = more recorded debt'}</small>
            {debtScore !== null && <div className="health-meter-track" title={`Recorded architectural debt: ${debtScore}/100`}>
              <div
                className="health-meter-fill"
                style={{
                  width: `${Math.min(100, Math.max(0, debtScore))}%`,
                  background: architecture.tone === 'neutral' ? 'var(--text-dim)' : architecture.tone === 'danger' ? 'var(--red)' : architecture.tone === 'warning' ? 'var(--orange)' : 'var(--green)'
                }}
              />
            </div>}
          </div>
          <div className="score-card">
            <span className="score-label">Architectural Smells</span>
            <strong className="score-value text-cyan">
              {findings.length}
            </strong>
            <small>{(severityCounts.critical || 0)} Critical · {(severityCounts.high || 0)} High</small>
          </div>
        </div>

        <EvidenceSummary result={result} />

        {!!result.policy_assessment?.rules?.length && (
          <section className="evidence-summary">
            <h3>Captured dependency rules</h3>
            <p>{result.policy_assessment.violations} violated · {result.policy_assessment.unresolved} unresolved. {result.policy_assessment.limitation}</p>
            <EvidenceDetails label="Rule evidence at analysis time" value={result.policy_assessment} />
          </section>
        )}

        {result.explanation && <p className="workspace-explanation">{result.explanation}</p>}

        {!!result.impacted_services?.length && (
          <div className="impacted-services-panel">
            <span className="panel-subtitle">Impacted services in this revision (open findings):</span>
            <div className="service-tags-interactive">
              {result.impacted_services.map((s, i) => (
                <a
                  key={i}
                  href={routeHash('projects', { projectId: demo ? 'demo' : result.project_id || '', jobId: result.analysis_id || result.id || '', view: 'findings' })}
                  className="service-tag clickable"
                  title={`Open findings for ${s}`}
                >
                  <span className="tag-dot" />
                  {s}
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Suggested fixes preview in Summary */}
        {suggestedFixes.length > 0 && (
          <section id="summary-recommendations" className="recommendations-section">
            <div className="recommendations-header-row">
              <div>
                <h3 className="recommendations-title">⚡ High-Impact Architectural Recommendations</h3>
                <p className="text-dim">Simulate counterfactual graph topology mutations directly beneath each recommendation.</p>
              </div>
              <span className="recommendation-badge-count">{suggestedFixes.length} available</span>
            </div>
            <div className="recommendations-list">
              {suggestedFixes.map((fix, index) => {
                const fixKey = `summary-rec-${index}`;
                const isActive = activeFixKey === fixKey;
                const isLoading = loadingFixKey === fixKey;
                const previewData = previewMap[fixKey];

                return (
                  <div key={index} className={`recommendation-card ${isActive ? 'active-fix' : ''}`}>
                    <div className="recommendation-header">
                      <div className="recommendation-icon">💡</div>
                      <div className="recommendation-content">
                        <div className="recommendation-title-row">
                          <h4 className="recommendation-title">
                            {typeof fix === 'string' ? fix : fix.title || 'Architectural Recommendation'}
                          </h4>
                        </div>
                        <p className="recommendation-desc">
                          {typeof fix === 'string' ? '' : fix.text || fix.description}
                        </p>

                        {/* Proposed edits preview pills */}
                        {fix.edits && fix.edits.length > 0 && (
                          <div className="recommendation-edits-summary">
                            <span className="edits-badge">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                              {fix.edits.length} proposed graph edit{fix.edits.length > 1 ? 's' : ''}
                            </span>
                            <div className="edits-list">
                              {fix.edits.map((e, ei) => (
                                <span key={ei} className="edit-pill">
                                  {graphEditLabel(e)}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Button triggering counterfactual preview */}
                        {!!fix.edits?.length && (
                          <div className="recommendation-actions">
                            <button
                              type="button"
                              disabled={loadingFixKey !== null && loadingFixKey !== fixKey}
                              className={`btn ${isActive ? 'btn-ghost active' : 'btn-primary-ghost'}`}
                              onClick={() => handleTogglePreview(fix, fixKey)}
                            >
                              {isLoading ? (
                                <><span className="spinner-xs" /> Simulating counterfactual…</>
                              ) : isActive ? (
                                '✕ Close Counterfactual'
                              ) : (
                                '⚡ Preview Graph Edits & Impact'
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* COUNTERFACTUAL PREVIEW: APPEARS RIGHT BELOW THE PREVIEW EDITS */}
                    {isActive && (
                      <CounterfactualPanel
                        previewData={previewData}
                        isLoading={isLoading}
                        error={fixError}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        <EvidenceDetails label="Full result and source evidence" value={result} />
      </article>
    );
  }

  /* ── Findings View ──────────────────────────────────────────── */
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageFindings = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <article className="card workspace-result findings-panel">
        {noticeError && <p role="alert" className="form-error">{noticeError}</p>}
      {/* Header */}
      <div className="findings-header">
        <div className="findings-header-text">
          <div className="summary-title-row">
            <h2>Findings & Counterfactuals</h2>
            <span className="findings-count-badge">{findings.length} findings</span>
            {suggestedFixes.length > 0 && (
              <span className="badge badge-warning" style={{ fontSize: '11px', padding: '2px 8px' }}>
                ⚡ {suggestedFixes.length} counterfactual fixes
              </span>
            )}
          </div>
          <p className="text-dim">Inspect architectural smells, preview remediations inline inside cards, or switch directly to counterfactual simulations.</p>
        </div>
        <div className="export-controls">
          <select className="form-select" aria-label="Export format" value={format} onChange={e => setFormat(e.target.value)}>
            <option value="md">Markdown (.md)</option>
            <option value="html">HTML Report</option>
            <option value="json">JSON Data</option>
          </select>
          <button className="btn btn-ghost" onClick={() => downloadAnalysis(result, format)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Export report
          </button>
        </div>
      </div>

      <EvidenceSummary result={result} />
      {!findings.length && <p role="status">No findings were supported by this captured evidence. Review coverage above; this does not establish a safe architecture.</p>}
      {/* Top Sub-Tab Switcher: Fixes the issue of counterfactual being stuck at the bottom! */}
      <div className="findings-subtabs">
        <button
          type="button"
          className={`findings-subtab-btn ${findingsSubView === 'findings' ? 'active' : ''}`}
          onClick={() => setFindingsSubView('findings')}
        >
          <span className="subtab-icon">🔍</span>
          <span>All Findings</span>
          <span className="subtab-count">{findings.length}</span>
        </button>
        <button
          type="button"
          className={`findings-subtab-btn ${findingsSubView === 'counterfactual' ? 'active' : ''}`}
          onClick={() => setFindingsSubView('counterfactual')}
        >
          <span className="subtab-icon">⚡</span>
          <span>Architectural Recommendations & Counterfactuals</span>
          <span className="subtab-count highlight">{suggestedFixes.length}</span>
        </button>
      </div>

      {/* ── VIEW 1: RECOMMENDATIONS & COUNTERFACTUALS (FRONT & CENTER) ── */}
      {findingsSubView === 'counterfactual' && (
        <section className="recommendations-section" style={{ marginTop: '4px' }}>
          <div className="recommendations-header-row">
            <div>
              <h3 className="recommendations-title">⚡ High-Impact Architectural Recommendations</h3>
              <p className="text-dim">Simulate counterfactual graph topology mutations directly beneath each recommendation card.</p>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setFindingsSubView('findings')}
            >
              ← Back to Findings list
            </button>
          </div>

          <div className="recommendations-list">
            {suggestedFixes.map((fix, index) => {
              const fixKey = `tab-rec-${index}`;
              const isActive = activeFixKey === fixKey;
              const isLoading = loadingFixKey === fixKey;
              const previewData = previewMap[fixKey];

              return (
                <div key={index} className={`recommendation-card ${isActive ? 'active-fix' : ''}`}>
                  <div className="recommendation-header">
                    <div className="recommendation-icon">💡</div>
                    <div className="recommendation-content">
                      <div className="recommendation-title-row">
                        <h4 className="recommendation-title">
                          {typeof fix === 'string' ? fix : fix.title || 'Architectural Recommendation'}
                        </h4>
                      </div>
                      <p className="recommendation-desc">
                        {typeof fix === 'string' ? '' : fix.text || fix.description}
                      </p>

                      {/* Proposed edits preview tags */}
                      {fix.edits && fix.edits.length > 0 && (
                        <div className="recommendation-edits-summary">
                          <span className="edits-badge">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                            {fix.edits.length} proposed graph edit{fix.edits.length > 1 ? 's' : ''}
                          </span>
                          <div className="edits-list">
                            {fix.edits.map((e, ei) => (
                              <span key={ei} className="edit-pill">
                                {graphEditLabel(e)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Button triggering counterfactual preview */}
                      {!!fix.edits?.length && (
                        <div className="recommendation-actions">
                          <button
                            type="button"
                            disabled={loadingFixKey !== null && loadingFixKey !== fixKey}
                            className={`btn ${isActive ? 'btn-ghost active' : 'btn-primary-ghost'}`}
                            onClick={() => handleTogglePreview(fix, fixKey)}
                          >
                            {isLoading ? (
                              <><span className="spinner-xs" /> Simulating counterfactual…</>
                            ) : isActive ? (
                              '✕ Close Counterfactual'
                            ) : (
                              '⚡ Preview Graph Edits & Impact'
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* COUNTERFACTUAL PREVIEW: APPEARS RIGHT BELOW THE PREVIEW EDITS */}
                  {isActive && (
                    <CounterfactualPanel
                      previewData={previewData}
                      isLoading={isLoading}
                      error={fixError}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── VIEW 2: ALL FINDINGS WITH INLINE REMEDIATION ── */}
      {findingsSubView === 'findings' && (
        <>
          {/* Severity overview pills */}
          {Object.keys(severityCounts).length > 0 && (
            <div className="severity-overview">
              {Object.entries(severityCounts)
                .sort(([a], [b]) => (SEVERITY_ORDER[a] ?? 99) - (SEVERITY_ORDER[b] ?? 99))
                .map(([sev, count]) => (
                  <button
                    key={sev}
                    type="button"
                    className={`severity-pill ${severityClass(sev)} ${severity === sev ? 'active' : ''}`}
                    onClick={() => { setSeverity(prev => prev === sev ? '' : sev); setPage(0); }}
                    title={`${severity === sev ? 'Clear' : 'Filter by'} ${sev}`}
                  >
                    <span className="severity-dot" />
                    <span className="severity-pill-label">{sev}</span>
                    <span className="severity-pill-count">{count}</span>
                  </button>
                ))}
            </div>
          )}

          {/* Search & Filter Toolbar */}
          <div className="findings-filters">
            <div className="search-box">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                className="form-input"
                aria-label="Search findings"
                value={query}
                onChange={e => { setQuery(e.target.value); setPage(0); }}
                placeholder="Search by service, rule, file or description…"
              />
              {query && (
                <button
                  type="button"
                  className="btn-clear-search"
                  onClick={() => { setQuery(''); setPage(0); }}
                  title="Clear search"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Severity filter */}
            <label className="severity-filter-label">
              Severity
              <select className="form-select" value={severity} onChange={e => { setSeverity(e.target.value); setPage(0); }}>
                <option value="">All severities</option>
                {severities.map(s => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
              </select>
            </label>

            {/* Service filter */}
            {allServices.length > 0 && (
              <label className="severity-filter-label">
                Service
                <select className="form-select" value={serviceFilter} onChange={e => { setServiceFilter(e.target.value); setPage(0); }}>
                  <option value="">All services ({allServices.length})</option>
                  {allServices.map(svc => <option key={svc} value={svc}>{svc}</option>)}
                </select>
              </label>
            )}

            {/* Sort selector */}
            <label className="severity-filter-label">
              Sort by
              <select className="form-select" value={sortBy} onChange={e => { setSortBy(e.target.value); setPage(0); }}>
                <option value="severity-desc">Severity (High to Low)</option>
                <option value="severity-asc">Severity (Low to High)</option>
                <option value="title-asc">Finding Title (A-Z)</option>
                <option value="service-asc">Primary Service (A-Z)</option>
              </select>
            </label>
          </div>

          {/* Active filters pill bar */}
          {(query || severity || serviceFilter) && (
            <div className="active-filter-strip">
              <span className="active-filter-title">Active filters:</span>
              {query && (
                <span className="active-filter-chip">
                  Query: <strong>"{query}"</strong>
                  <button type="button" onClick={() => setQuery('')}>✕</button>
                </span>
              )}
              {severity && (
                <span className={`active-filter-chip ${severityClass(severity)}`}>
                  Severity: <strong>{severity.toUpperCase()}</strong>
                  <button type="button" onClick={() => setSeverity('')}>✕</button>
                </span>
              )}
              {serviceFilter && (
                <span className="active-filter-chip service">
                  Service: <strong>{serviceFilter}</strong>
                  <button type="button" onClick={() => setServiceFilter('')}>✕</button>
                </span>
              )}
              <button type="button" className="btn-clear-all" onClick={handleClearAllFilters}>
                Clear all filters
              </button>
            </div>
          )}

          {/* Status & view control bar */}
          <div className="findings-status-bar">
            <p className="findings-match-count" role="status">
              {filtered.length === findings.length
                ? `Showing all ${findings.length} findings`
                : `${filtered.length} of ${findings.length} findings match criteria`}
            </p>

            <div className="findings-status-actions">
              {suggestedFixes.length > 0 && (
                <button
                  type="button"
                  className="btn-counterfactual-quickpill"
                  onClick={() => setFindingsSubView('counterfactual')}
                  title="Switch to Recommendations & Counterfactuals view"
                >
                  ⚡ {suggestedFixes.length} Counterfactual Previews Available →
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setExpandAll(prev => !prev)}
                title={expandAll ? 'Collapse all finding details' : 'Expand all finding details'}
              >
                {expandAll ? '⊟ Collapse All' : '⊞ Expand All'}
              </button>
            </div>
          </div>

          {/* Finding cards */}
          <div className="findings-list">
            {pageFindings.map((f, index) => {
              const globalIndex = page * PAGE_SIZE + index;
              const findingId = f.id || `f-${globalIndex}`;
              const isExpanded = expandAll || expandedId === findingId;
              const isCopied = copiedId === findingId;

              // Check if finding matches any proposed fix
              const matchingFix = findMatchingFix(f);
              const fixKey = `finding-${findingId}`;
              const isFixActive = activeFixKey === fixKey;
              const isFixLoading = loadingFixKey === fixKey;
              const previewData = previewMap[fixKey];

              return (
                <div
                  key={findingId}
                  className={`finding-card ${severityClass(f.severity)} ${isExpanded ? 'expanded' : ''}`}
                >
                  {/* Card header */}
                  <div
                    className="finding-card-header"
                    onClick={() => {
                      if (expandAll) setExpandAll(false);
                      setExpandedId(expandedId === findingId ? null : findingId);
                    }}
                  >
                    <div className="finding-card-title-row">
                      <span className={`finding-severity-badge ${severityClass(f.severity)}`}>
                        {String(f.severity || 'info').toUpperCase()}
                      </span>
                      <h3 className="finding-title">{f.type || f.title || 'Finding'}</h3>

                      {matchingFix && (
                        <span className="badge-fix-available" title="Proposed graph remediation & counterfactual preview available">
                          ⚡ Fix Available
                        </span>
                      )}

                      <div className="finding-card-tools" onClick={e => e.stopPropagation()}>
                        <button
                          type="button"
                          className={`btn-copy-finding ${isCopied ? 'copied' : ''}`}
                          onClick={e => copyFindingMarkdown(f, e)}
                          title="Copy finding summary as Markdown"
                        >
                          {isCopied ? '✓ Copied' : '📋 Copy'}
                        </button>
                        <button
                          type="button"
                          className="finding-expand-btn"
                          aria-label={isExpanded ? 'Collapse' : 'Expand'}
                          onClick={() => {
                            if (expandAll) setExpandAll(false);
                            setExpandedId(expandedId === findingId ? null : findingId);
                          }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transform: isExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    <p className="finding-description">{f.description || f.message}</p>
                  </div>

                  {/* Expanded detail content */}
                  {isExpanded && (
                    <div className="finding-card-body">
                      {f.services && f.services.length > 0 && (
                        <div className="finding-meta-row">
                          <span className="finding-meta-label">Services</span>
                          <div className="finding-meta-value service-tags">
                            {f.services.map((s, i) => (
                              <button
                                key={i}
                                type="button"
                                className={`service-tag clickable ${serviceFilter === s ? 'active' : ''}`}
                                onClick={e => {
                                  e.stopPropagation();
                                  setServiceFilter(prev => prev === s ? '' : s);
                                  setPage(0);
                                }}
                                title={`Filter findings by ${s}`}
                              >
                                <span className="tag-dot" />
                                {s}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {f.file_path && (
                        <div className="finding-meta-row">
                          <span className="finding-meta-label">Location</span>
                          <code className="finding-file-path">{f.file_path}{f.line && `:${f.line}`}</code>
                        </div>
                      )}

                      {f.rule && (
                        <div className="finding-meta-row">
                          <span className="finding-meta-label">Rule</span>
                          <span className="finding-meta-value font-mono">{f.rule}</span>
                        </div>
                      )}

                      {f.category && (
                        <div className="finding-meta-row">
                          <span className="finding-meta-label">Category</span>
                          <span className="finding-meta-value">{f.category}</span>
                        </div>
                      )}

                      {/* INLINE REMEDIATION & COUNTERFACTUAL: APPEARS RIGHT INSIDE THE FINDING CARD */}
                      {matchingFix && (
                        <div className="finding-remediation-box">
                          <div className="remediation-header-row">
                            <span className="remediation-badge">⚡ Recommended Architectural Remediation</span>
                          </div>
                          <h4 className="remediation-title">{matchingFix.title}</h4>
                          <p className="remediation-desc">{matchingFix.description}</p>

                          {/* Proposed preview edits */}
                          {matchingFix.edits && matchingFix.edits.length > 0 && (
                            <div className="remediation-preview-edits">
                              <span className="edits-badge">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                                {matchingFix.edits.length} proposed graph edit{matchingFix.edits.length > 1 ? 's' : ''}
                              </span>
                              <div className="edits-list">
                                {matchingFix.edits.map((e, ei) => (
                                  <span key={ei} className="edit-pill">
                                    {graphEditLabel(e)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Button triggering counterfactual preview */}
                          <div className="remediation-action-row">
                            <button
                              type="button"
                              disabled={loadingFixKey !== null && loadingFixKey !== fixKey}
                              className={`btn ${isFixActive ? 'btn-ghost active' : 'btn-primary-ghost'}`}
                              onClick={() => handleTogglePreview(matchingFix, fixKey)}
                            >
                              {isFixLoading ? (
                                <><span className="spinner-xs" /> Simulating counterfactual…</>
                              ) : isFixActive ? (
                                '✕ Close Counterfactual'
                              ) : (
                                '⚡ Preview Graph Edits & Counterfactual Impact'
                              )}
                            </button>
                          </div>

                          {/* COUNTERFACTUAL PREVIEW: APPEARS RIGHT BELOW THE PREVIEW EDITS */}
                          {isFixActive && (
                            <CounterfactualPanel
                              previewData={previewData}
                              isLoading={isFixLoading}
                              error={fixError}
                            />
                          )}
                        </div>
                      )}

                      <EvidenceDetails label="View raw evidence payload" value={f} />

                      {!demo && analysisId && f.id && (
                        <div className="finding-review-section">
                          <FindingReview
                            key={`${f.id}:${reviews[f.id]?.updated_at || ''}`}
                            analysisId={analysisId}
                            findingId={f.id}
                            review={reviews[f.id]}
                            onSave={review => setReviews(previous => ({ ...previous, [f.id]: review }))}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="findings-pagination">
              <button className="btn btn-ghost" disabled={!page} onClick={() => setPage(v => v - 1)}>
                ← Previous
              </button>
              <div className="pagination-info">
                <span className="pagination-current">Page {page + 1}</span>
                <span className="text-dim">of {totalPages}</span>
              </div>
              <button className="btn btn-ghost" disabled={(page + 1) * PAGE_SIZE >= filtered.length} onClick={() => setPage(v => v + 1)}>
                Next →
              </button>
            </div>
          )}
        </>
      )}

      {/* Floating Scroll-to-Top Button */}
      {showScrollTop && (
        <button
          type="button"
          className="btn-scroll-top"
          onClick={scrollToTop}
          title="Scroll back to top"
          aria-label="Scroll back to top"
        >
          ↑ Top
        </button>
      )}
    </article>
  );
}
