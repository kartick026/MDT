import { useEffect, useMemo, useRef, useState } from 'react';
import { getFindingReviews, previewAnalysis } from '../api';
import { downloadAnalysis, formatScore, routeHash, architectureSummary } from '../utils/analysis';
import EvidenceSummary from './EvidenceSummary';
import FindingReview from './FindingReview';
import EvidenceDetails from './EvidenceDetails';
import CounterfactualPanel, { ProposedChange } from './RemediationPreview';
import CustomSelect from './CustomSelect';
import { Check, Copy, FlaskConical, Lightbulb, Network, ScanSearch } from 'lucide-react';


const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const severityClass = s => {
  const key = String(s || '').toLowerCase();
  if (key === 'critical') return 'severity-critical';
  if (key === 'high') return 'severity-high';
  if (key === 'medium') return 'severity-medium';
  if (key === 'low') return 'severity-low';
  return 'severity-info';
};

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
      if (finding.id && (fix.finding_id === finding.id || fix.finding_ids?.includes(finding.id))) return true;
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
      if (err.code !== 'ERR_CANCELED') setFixError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : err.message || 'Simulation failed');
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
                  {copiedMeta ? <><Check size={14} aria-hidden="true" />Copied</> : <Copy size={14} aria-label="Copy commit SHA" />}
                </button>
              )}
            </div>
          </div>
          <div className="export-controls">
            <CustomSelect className="form-select" aria-label="Export format" value={format} onChange={e => setFormat(e.target.value)}>
              <option value="md">Markdown (.md)</option>
              <option value="html">HTML Report</option>
              <option value="json">JSON Data</option>
            </CustomSelect>
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
            <ScanSearch size={16} aria-hidden="true" />
            <span className="action-pill-text"><strong>Review {findings.length} Findings</strong></span>
            <span className="action-pill-count">{findings.length}</span>
          </a>
          <a
            href={routeHash('projects', { projectId: demo ? 'demo' : result.project_id || '', jobId: result.analysis_id || result.id || '', view: 'graph' })}
            className="action-pill"
          >
            <Network size={16} aria-hidden="true" />
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
              <FlaskConical size={16} aria-hidden="true" />
              <span className="action-pill-text">Explore {suggestedFixes.length} possible changes</span>
              <span className="action-pill-count">{suggestedFixes.length}</span>
            </button>
          )}
          {!demo && (
            <a
              href={routeHash('projects', { projectId: result.project_id || '', view: 'analyze' })}
              className="action-pill"
            >
              <ScanSearch size={16} aria-hidden="true" />
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
                <h3 className="recommendations-title">Possible architecture changes</h3>
                <p className="text-dim">Explore a design option, check its result, then decide whether to implement it.</p>
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
                      <div className="recommendation-icon"><Lightbulb size={19} aria-hidden="true" /></div>
                      <div className="recommendation-content">
                        <ProposedChange fix={fix} findings={findings} />

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
                                <><span className="spinner-xs" /> Checking proposed change…</>
                              ) : isActive ? (
                                'Close simulation'
                              ) : (
                                'Test this change'
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
            <h2>Findings & possible changes</h2>
            <span className="findings-count-badge">{findings.length} findings</span>
            {suggestedFixes.length > 0 && (
              <span className="badge badge-warning" style={{ fontSize: '11px', padding: '2px 8px' }}>
                <FlaskConical size={15} aria-hidden="true" />{suggestedFixes.length} possible changes
              </span>
            )}
          </div>
          <p className="text-dim">Review findings and explore possible changes. Each simulation explains its result and the next step.</p>
        </div>
        <div className="export-controls">
          <CustomSelect className="form-select" aria-label="Export format" value={format} onChange={e => setFormat(e.target.value)}>
            <option value="md">Markdown (.md)</option>
            <option value="html">HTML Report</option>
            <option value="json">JSON Data</option>
          </CustomSelect>
          <button className="btn btn-ghost" onClick={() => downloadAnalysis(result, format)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Export report
          </button>
        </div>
      </div>

      <details className="evidence-disclosure">
        <summary>Analysis evidence and coverage <span>{demo ? 'Recorded example' : 'Captured evidence'}</span></summary>
        <EvidenceSummary result={result} />
      </details>
      {!findings.length && <p role="status">No findings were supported by this captured evidence. Review coverage above; this does not establish a safe architecture.</p>}
      {/* Top Sub-Tab Switcher: Fixes the issue of counterfactual being stuck at the bottom! */}
      <div className="findings-subtabs">
        <button
          type="button"
          className={`findings-subtab-btn ${findingsSubView === 'findings' ? 'active' : ''}`}
          onClick={() => setFindingsSubView('findings')}
        >
          <ScanSearch size={16} aria-hidden="true" />
          <span>All Findings</span>
          <span className="subtab-count">{findings.length}</span>
        </button>
        <button
          type="button"
          className={`findings-subtab-btn ${findingsSubView === 'counterfactual' ? 'active' : ''}`}
          onClick={() => setFindingsSubView('counterfactual')}
        >
          <FlaskConical size={16} aria-hidden="true" />
          <span>Explore possible changes</span>
          <span className="subtab-count highlight">{suggestedFixes.length}</span>
        </button>
      </div>

      {/* ── VIEW 1: RECOMMENDATIONS & COUNTERFACTUALS (FRONT & CENTER) ── */}
      {findingsSubView === 'counterfactual' && (
        <section className="recommendations-section" style={{ marginTop: '4px' }}>
          <div className="recommendations-header-row">
            <div>
              <h3 className="recommendations-title">Possible architecture changes</h3>
              <p className="text-dim">These are proposals to test. A simulation can show improvement, no benefit, or a worse result.</p>
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
                    <div className="recommendation-icon"><Lightbulb size={19} aria-hidden="true" /></div>
                    <div className="recommendation-content">
                      <ProposedChange fix={fix} findings={findings} />

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
                              <><span className="spinner-xs" /> Checking proposed change…</>
                            ) : isActive ? (
                              'Close simulation'
                            ) : (
                              'Test this change'
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
              <CustomSelect className="form-select" aria-label="Severity" value={severity} onChange={e => { setSeverity(e.target.value); setPage(0); }}>
                <option value="">All severities</option>
                {severities.map(s => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
              </CustomSelect>
            </label>

            {/* Service filter */}
            {allServices.length > 0 && (
              <label className="severity-filter-label">
                Service
                <CustomSelect className="form-select" aria-label="Service" value={serviceFilter} onChange={e => { setServiceFilter(e.target.value); setPage(0); }}>
                  <option value="">All services ({allServices.length})</option>
                  {allServices.map(svc => <option key={svc} value={svc}>{svc}</option>)}
                </CustomSelect>
              </label>
            )}

            {/* Sort selector */}
            <label className="severity-filter-label">
              Sort by
              <CustomSelect className="form-select" aria-label="Sort by" value={sortBy} onChange={e => { setSortBy(e.target.value); setPage(0); }}>
                <option value="severity-desc">Severity (High to Low)</option>
                <option value="severity-asc">Severity (Low to High)</option>
                <option value="title-asc">Finding Title (A-Z)</option>
                <option value="service-asc">Primary Service (A-Z)</option>
              </CustomSelect>
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
                  title="Explore possible architecture changes"
                >
                  <FlaskConical size={15} aria-hidden="true" />{suggestedFixes.length} possible changes to explore →
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
                        <span className="badge-fix-available" title="A possible change is available to test">
                          <Lightbulb size={12} aria-hidden="true" /> Possible change
                        </span>
                      )}

                      <div className="finding-card-tools" onClick={e => e.stopPropagation()}>
                        <button
                          type="button"
                          className={`btn-copy-finding ${isCopied ? 'copied' : ''}`}
                          onClick={e => copyFindingMarkdown(f, e)}
                          title="Copy finding summary as Markdown"
                        >
                          {isCopied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}{isCopied ? 'Copied' : 'Copy'}
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
                          </div>
                          <ProposedChange fix={matchingFix} findings={findings} />

                          {/* Button triggering counterfactual preview */}
                          <div className="remediation-action-row">
                            <button
                              type="button"
                              disabled={loadingFixKey !== null && loadingFixKey !== fixKey}
                              className={`btn ${isFixActive ? 'btn-ghost active' : 'btn-primary-ghost'}`}
                              onClick={() => handleTogglePreview(matchingFix, fixKey)}
                            >
                              {isFixLoading ? (
                                <><span className="spinner-xs" /> Checking proposed change…</>
                              ) : isFixActive ? (
                                'Close simulation'
                              ) : (
                                'Test this change'
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
