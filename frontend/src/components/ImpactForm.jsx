import { useState } from 'react';
import { analyzeImpact, previewFix } from '../api';

const RISK_COLORS = {
  LOW: 'var(--green)', MEDIUM: 'var(--yellow)',
  HIGH: 'var(--orange)', CRITICAL: 'var(--red)',
  low: 'var(--green)', medium: 'var(--yellow)',
  high: 'var(--orange)', critical: 'var(--red)'
};

function ScoreGauge({ score, level, size = 120 }) {
  const r = (size / 2) - 10;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (score / 100) * circumference;
  const color = RISK_COLORS[level] || 'var(--text-faint)';
  const strokeWidth = size > 100 ? 9 : 6;
  const scoreFontSize = size > 100 ? 22 : 16;
  const labelFontSize = size > 100 ? 10 : 8;

  return (
    <div className="gauge-wrap" style={{ width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={strokeWidth} />
        <circle
          cx={cx} cy={cy} r={r} fill="none"
          stroke={color} strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: 'stroke-dashoffset .9s cubic-bezier(0.16,1,.3,1), stroke .4s' }}
        />
        <text x={cx} y={cy - (size > 100 ? 4 : 2)} textAnchor="middle" fill="white" fontSize={scoreFontSize} fontWeight="700" fontFamily="'JetBrains Mono', monospace">{score}</text>
        <text x={cx} y={cy + (size > 100 ? 14 : 11)} textAnchor="middle" fill={color} fontSize={labelFontSize} fontFamily="Inter,sans-serif" fontWeight="600" style={{textTransform:'uppercase'}}>{level}</text>
      </svg>
    </div>
  );
}

export default function ImpactForm({ onAnalysis }) {
  const [repoUrls, setRepoUrls] = useState('https://github.com/kartick026/MDT');
  const [commitSha, setCommitSha] = useState('main');
  const [files, setFiles] = useState('');

  const [results,  setResults]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  // What-If Preview state
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [activePreviewIdx, setActivePreviewIdx] = useState(null);

  // Detail section tabs & file search
  const [detailTab, setDetailTab] = useState('recommendations'); // 'recommendations' | 'files' | 'services' | 'all'
  const [fileFilter, setFileFilter] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!repoUrls || !commitSha) return;
    setLoading(true); setError(null);
    setPreviewData(null); setActivePreviewIdx(null);
    try {
      const repos = repoUrls.split(',').map(r => r.trim()).filter(r => r);
      const changedFiles = files.trim() ? files.split(',').map(f => f.trim()).filter(f => f) : null;
      
      const promises = repos.map(repo => analyzeImpact({
        repo_url: repo,
        commit_sha: commitSha,
        ...(changedFiles && changedFiles.length > 0 ? { changed_files: changedFiles } : {}),
      }));
      
      const data = await Promise.all(promises);
      setResults(data);
      onAnalysis?.();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Backend unreachable — is it running on :8000?');
    } finally {
      setLoading(false);
    }
  };

  const handlePreviewFix = async (edits, idx) => {
    if (activePreviewIdx === idx) {
      setPreviewData(null);
      setActivePreviewIdx(null);
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    setActivePreviewIdx(idx);
    try {
      const data = await previewFix({ edits });
      setPreviewData(data);
    } catch (err) {
      setPreviewError(err.response?.data?.detail || err.message || 'Preview failed');
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const loadSample = () => {
    setRepoUrls('https://github.com/kartick026/MDT');
    setCommitSha('main');
    setFiles('services/payment_service/main.py, services/user_service/main.py');
  };

  // Parse structured edits from suggestion if explicitly provided for graph remediations
  const tryParseEdits = (suggestion) => {
    if (typeof suggestion === 'object' && suggestion.edits && Array.isArray(suggestion.edits) && suggestion.edits.length > 0) {
      return suggestion.edits;
    }
    return null;
  };

  return (
    <div className="impact-split">
      {/* Left: Configure Form */}
      <div className="impact-panel" style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        position: 'sticky',
        top: '76px',
        alignSelf: 'start',
        maxHeight: 'calc(100vh - 96px)',
        overflowY: 'auto'
      }}>
        <div>
          <div className="panel-title" style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--display)' }}>Configure Analysis</div>
          <div className="text-dim text-xs" style={{ marginTop: '2px' }}>Target a repository and commit to run the HMDA drift analysis</div>
        </div>

        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div className="form-field">
            <label className="form-label" style={{ fontSize: '11.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-dim)' }}>
              Repository URL
            </label>
            <input
              className="form-input"
              type="text"
              value={repoUrls}
              onChange={e => setRepoUrls(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
            />
          </div>

          <div className="form-field">
            <label className="form-label" style={{ fontSize: '11.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-dim)' }}>
              Commit SHA (or branch ref)
            </label>
            <input
              className="form-input"
              type="text"
              value={commitSha}
              onChange={e => setCommitSha(e.target.value)}
              placeholder="main"
              required
            />
          </div>

          <div className="form-field">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <label className="form-label" style={{ fontSize: '11.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-dim)' }}>
                Changed Files (Optional)
              </label>
              <button type="button" className="btn btn-ghost" onClick={loadSample} style={{ padding: '2px 8px', fontSize: '11px' }}>
                Load sample
              </button>
            </div>
            <textarea
              className="diff-editor"
              placeholder={"Leave blank to automatically detect all changed files in this commit from GitHub\nOr specify: services/order_service/main.py, services/user_service/main.py"}
              value={files}
              onChange={e => setFiles(e.target.value)}
              rows={4}
              style={{ minHeight: '140px', fontSize: '12px' }}
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading} style={{ height: '42px', width: '100%', justifyContent: 'center' }}>
            {loading ? <><span className="spinner-xs" /> Analyzing Commit…</> : '⚡ Run HMDA Analysis'}
          </button>
          {error && <div className="form-error">{error}</div>}
        </form>
      </div>

      {/* Right: Results Dashboard */}
      <div className="impact-panel" style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        minHeight: '480px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div className="panel-title" style={{ fontSize: '18px', fontWeight: 600, fontFamily: 'var(--display)' }}>Analysis Result</div>
            <div className="text-dim text-xs" style={{ marginTop: '2px' }}>Live hierarchical microservice drift analysis output</div>
          </div>
          {results && results.length > 0 && (
            <span style={{ fontSize: '11px', color: 'var(--cyan)', background: 'rgba(0, 212, 255, 0.08)', border: '1px solid rgba(0, 212, 255, 0.2)', padding: '4px 10px', borderRadius: '12px', fontWeight: 600 }}>
              Live Report
            </span>
          )}
        </div>

        {!results && !loading && (
          <div className="result-placeholder" style={{ minHeight: '360px' }}>
            <div className="result-placeholder-icon" style={{ fontSize: '42px', opacity: 0.3 }}>⚡</div>
            <p className="text-sm text-dim">Configure a target repository and click <strong>Run HMDA Analysis</strong> to generate the live blast-radius and remediation report.</p>
          </div>
        )}

        {loading && (
          <div className="state-loading" style={{ minHeight: '360px' }}>
            <div className="spinner" />
            <span className="text-dim text-sm">Fetching commit diff & calculating architectural risk…</span>
          </div>
        )}

        {results && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
            {results.map((result, idx) => (
              <div key={idx} className="result-panel anim-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                {/* Result Header Card */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid var(--border)',
                  borderRadius: '12px',
                  padding: '16px 20px',
                  gap: '16px'
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
                    <div style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'var(--display)', color: 'var(--text)' }}>
                      {result.repo_url ? result.repo_url.replace(/\.git$/i, '').split('/').slice(-2).join('/') : 'Target Repository'}
                      <span className="text-mono" style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-dim)', marginLeft: '8px' }}>
                        @{result.commit?.substring(0, 7) || 'head'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '2px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                        Confidence: <strong style={{ color: 'var(--cyan)' }}>{(result.confidence * 100).toFixed(0)}%</strong>
                      </span>
                      <span style={{ color: 'var(--border)' }}>•</span>
                      <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                        Files Affected: <strong style={{ color: 'var(--text)' }}>{result.affected_files?.length || 0}</strong>
                      </span>
                    </div>
                  </div>
                  <ScoreGauge score={Math.round(result.risk_score)} level={result.severity} size={105} />
                </div>

                {/* Connection Bugs Alert Banner */}
                {result.connection_bugs?.length > 0 && (
                  <div style={{
                    background: 'rgba(255, 45, 85, 0.06)',
                    border: '1px solid rgba(255, 45, 85, 0.3)',
                    borderRadius: '10px',
                    padding: '14px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px'
                  }}>
                    <div style={{ color: 'var(--red)', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span>⚠</span> Connection Integrity Errors ({result.connection_bugs.length})
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {result.connection_bugs.map((b, i) => (
                        <div key={i} style={{ fontSize: '12px', lineHeight: '1.4', background: 'rgba(0,0,0,0.2)', padding: '8px 10px', borderRadius: '6px' }}>
                          <span style={{ color: 'var(--red)', fontWeight: '600' }}>[{b.bug_type}]</span> {b.description}
                          <div className="text-dim text-xs" style={{ marginTop: '2px' }}>💡 {b.suggestion}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Summary / Explanation */}
                {result.explanation && (
                  <div style={{
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    padding: '12px 16px',
                    fontSize: '13px',
                    lineHeight: '1.5',
                    color: 'var(--text-dim)'
                  }}>
                    {result.explanation.replace(/\*\*/g,'')}
                  </div>
                )}

                {/* Segmented Detail View Switcher */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '10px',
                  borderBottom: '1px solid var(--border)',
                  paddingBottom: '14px',
                  marginTop: '4px'
                }}>
                  <div style={{
                    display: 'flex',
                    gap: '4px',
                    padding: '3px',
                    background: 'rgba(0, 0, 0, 0.4)',
                    borderRadius: '8px',
                    border: '1px solid var(--border)'
                  }}>
                    <button
                      type="button"
                      onClick={() => setDetailTab('recommendations')}
                      style={{
                        padding: '6px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        borderRadius: '6px',
                        border: 'none',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        background: detailTab === 'recommendations' ? 'var(--blue)' : 'transparent',
                        color: detailTab === 'recommendations' ? 'white' : 'var(--text-dim)',
                        boxShadow: detailTab === 'recommendations' ? '0 2px 10px rgba(58, 134, 255, 0.35)' : 'none'
                      }}
                    >
                      💡 Recommendations ({result.suggested_fixes?.length || 1})
                    </button>
                    <button
                      type="button"
                      onClick={() => setDetailTab('files')}
                      style={{
                        padding: '6px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        borderRadius: '6px',
                        border: 'none',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        background: detailTab === 'files' ? 'var(--blue)' : 'transparent',
                        color: detailTab === 'files' ? 'white' : 'var(--text-dim)',
                        boxShadow: detailTab === 'files' ? '0 2px 10px rgba(58, 134, 255, 0.35)' : 'none'
                      }}
                    >
                      📁 Affected Files ({result.affected_files?.length || 0})
                    </button>
                    <button
                      type="button"
                      onClick={() => setDetailTab('services')}
                      style={{
                        padding: '6px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        borderRadius: '6px',
                        border: 'none',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        background: detailTab === 'services' ? 'var(--blue)' : 'transparent',
                        color: detailTab === 'services' ? 'white' : 'var(--text-dim)',
                        boxShadow: detailTab === 'services' ? '0 2px 10px rgba(58, 134, 255, 0.35)' : 'none'
                      }}
                    >
                      🌐 Blast Radius ({result.impacted_services?.length || 0})
                    </button>
                    <button
                      type="button"
                      onClick={() => setDetailTab('all')}
                      style={{
                        padding: '6px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        borderRadius: '6px',
                        border: 'none',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        background: detailTab === 'all' ? 'rgba(255,255,255,0.1)' : 'transparent',
                        color: detailTab === 'all' ? 'white' : 'var(--text-dim)'
                      }}
                    >
                      📋 View All
                    </button>
                  </div>
                </div>

                {/* Tab: Recommendations & Remediation */}
                {(detailTab === 'recommendations' || detailTab === 'all') && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ fontSize: '11.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-dim)' }}>
                      Recommendations & Remediation ({result.suggested_fixes?.length || 1})
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {(result.suggested_fixes && result.suggested_fixes.length > 0
                        ? result.suggested_fixes
                        : [`Introduce resilience facade for '${result.impacted_services?.[0] || 'order-service'}' to isolate downstream failure cascade.`]
                      ).map((r, i) => {
                        const fixText = typeof r === 'object' ? r.text : r;
                        const edits = tryParseEdits(r, result);
                        const isPreviewActive = activePreviewIdx === `${idx}-${i}`;

                        return (
                          <div key={i} style={{
                            background: isPreviewActive ? 'rgba(0, 212, 255, 0.03)' : 'rgba(255, 255, 255, 0.02)',
                            border: isPreviewActive ? '1px solid rgba(0, 212, 255, 0.35)' : '1px solid var(--border)',
                            borderRadius: '10px',
                            padding: '16px 18px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '14px',
                            transition: 'border-color 0.2s, background 0.2s'
                          }}>
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
                              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', flex: '1 1 auto', minWidth: 0 }}>
                                <span style={{ fontSize: '16px', marginTop: '1px', flexShrink: 0 }}>💡</span>
                                <span style={{ fontSize: '13.5px', lineHeight: '1.5', color: 'var(--text)', wordBreak: 'break-word' }}>{fixText}</span>
                              </div>

                              {edits && edits.length > 0 && (
                                <button
                                  type="button"
                                  onClick={() => handlePreviewFix(edits, `${idx}-${i}`)}
                                  disabled={previewLoading}
                                  style={{
                                    flexShrink: 0,
                                    whiteSpace: 'nowrap',
                                    fontSize: '11.5px',
                                    fontWeight: 600,
                                    padding: '6px 14px',
                                    borderRadius: '6px',
                                    cursor: 'pointer',
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '6px',
                                    transition: 'all 0.2s',
                                    background: isPreviewActive ? 'rgba(255, 45, 85, 0.12)' : 'rgba(0, 212, 255, 0.08)',
                                    border: isPreviewActive ? '1px solid rgba(255, 45, 85, 0.35)' : '1px solid rgba(0, 212, 255, 0.3)',
                                    color: isPreviewActive ? 'var(--red)' : 'var(--cyan)',
                                    outline: 'none'
                                  }}
                                >
                                  {previewLoading && isPreviewActive ? (
                                    <><span className="spinner-xs" /> Simulating…</>
                                  ) : isPreviewActive ? (
                                    '✕ Close'
                                  ) : (
                                    '⚡ Preview Fix Impact'
                                  )}
                                </button>
                              )}
                            </div>

                            {/* What-If Preview Panel (inline) */}
                            {isPreviewActive && previewData && !previewLoading && (
                              <div style={{
                                background: 'rgba(8, 12, 24, 0.95)',
                                border: '1px solid rgba(0, 212, 255, 0.25)',
                                borderRadius: '8px',
                                padding: '16px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '14px',
                                boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                                marginTop: '4px'
                              }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                                  <span style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--cyan)', textTransform: 'uppercase' }}>
                                    ⚡ What-If Architectural Smell Preview
                                  </span>
                                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--green)', background: 'rgba(0, 255, 136, 0.08)', border: '1px solid rgba(0, 255, 136, 0.25)', padding: '2px 10px', borderRadius: '12px' }}>
                                    ✓ Sandbox Mode (Live Graph Unchanged)
                                  </span>
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '-8px' }}>
                                  Simulates architectural smell risk reduction on sandbox graph (0–100 scale, distinct from commit drift score)
                                </div>

                                {/* Comparison Gauge Row */}
                                <div style={{
                                  display: 'grid',
                                  gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                                  alignItems: 'center',
                                  justifyItems: 'center',
                                  gap: '16px',
                                  padding: '14px',
                                  background: 'rgba(255, 255, 255, 0.015)',
                                  borderRadius: '8px',
                                  border: '1px solid rgba(255, 255, 255, 0.04)'
                                }}>
                                  {/* Before */}
                                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                                    <span style={{ fontSize: '10.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)' }}>Before (Smell Risk)</span>
                                    <ScoreGauge score={Math.round(previewData.before.score)} level={previewData.before.severity} size={82} />
                                    <span style={{ fontSize: '11px', color: 'var(--text-faint)', fontFamily: 'var(--mono)' }}>
                                      {previewData.before.total_smells} smell{previewData.before.total_smells !== 1 ? 's' : ''}
                                    </span>
                                  </div>

                                  {/* Arrow & Delta Badge */}
                                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                                    <span style={{ fontSize: '20px', color: 'var(--cyan)', opacity: 0.8 }}>→</span>
                                    <div style={{
                                      fontSize: '11.5px',
                                      fontWeight: 700,
                                      padding: '4px 10px',
                                      borderRadius: '6px',
                                      background: previewData.delta.score_reduction > 0 ? 'rgba(0, 255, 136, 0.1)' : previewData.delta.score_reduction < 0 ? 'rgba(255, 45, 85, 0.1)' : 'rgba(255, 255, 255, 0.05)',
                                      border: previewData.delta.score_reduction > 0 ? '1px solid rgba(0, 255, 136, 0.3)' : previewData.delta.score_reduction < 0 ? '1px solid rgba(255, 45, 85, 0.3)' : '1px solid rgba(255, 255, 255, 0.1)',
                                      color: previewData.delta.score_reduction > 0 ? 'var(--green)' : previewData.delta.score_reduction < 0 ? 'var(--red)' : 'var(--text-dim)',
                                      whiteSpace: 'nowrap'
                                    }}>
                                      {previewData.delta.score_reduction > 0 ? '▼' : previewData.delta.score_reduction < 0 ? '▲' : '—'}{' '}
                                      {Math.abs(previewData.delta.score_reduction)} pts {previewData.delta.score_reduction > 0 ? 'Reduction' : previewData.delta.score_reduction < 0 ? 'Increase' : 'Unchanged'}
                                    </div>
                                  </div>

                                  {/* After */}
                                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                                    <span style={{ fontSize: '10.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)' }}>After (Smell Risk)</span>
                                    <ScoreGauge score={Math.round(previewData.after.score)} level={previewData.after.severity} size={82} />
                                    <span style={{ fontSize: '11px', color: 'var(--text-faint)', fontFamily: 'var(--mono)' }}>
                                      {previewData.after.total_smells} smell{previewData.after.total_smells !== 1 ? 's' : ''}
                                    </span>
                                  </div>
                                </div>

                                {previewData.delta?.measurable_change === false && (
                                  <div style={{
                                    fontSize: '11.5px',
                                    color: 'var(--text-dim)',
                                    background: 'rgba(255, 255, 255, 0.03)',
                                    border: '1px dashed rgba(255, 255, 255, 0.15)',
                                    padding: '8px 12px',
                                    borderRadius: '6px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px'
                                  }}>
                                    <span>ℹ</span>
                                    <span>No measurable change in tracked architectural smells (0 → 0). The previewed edit does not affect the 4 tracked topological smells.</span>
                                  </div>
                                )}

                                {/* Smells Breakdown List */}
                                <div style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: '6px',
                                  padding: '10px 14px',
                                  background: 'rgba(0, 0, 0, 0.3)',
                                  borderRadius: '6px',
                                  border: '1px solid rgba(255, 255, 255, 0.04)'
                                }}>
                                  <span style={{ fontSize: '10.5px', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '2px' }}>
                                    Architectural Smells Impact
                                  </span>
                                  {Object.entries(previewData.before.smells).map(([key, val]) => {
                                    const afterVal = previewData.after.smells[key] || 0;
                                    const diff = val - afterVal;
                                    if (val === 0 && afterVal === 0) return null;
                                    return (
                                      <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                                        <span style={{ color: 'var(--text)', textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                                        <span style={{ fontFamily: 'var(--mono)' }}>
                                          {val} → {afterVal}
                                          {diff > 0 && <span style={{ color: 'var(--green)', fontWeight: 600, marginLeft: '6px' }}>(-{diff} resolved)</span>}
                                          {diff < 0 && <span style={{ color: 'var(--red)', fontWeight: 600, marginLeft: '6px' }}>(+{Math.abs(diff)} introduced)</span>}
                                        </span>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            {isPreviewActive && previewError && (
                              <div className="form-error" style={{ fontSize: '12px', marginTop: '4px' }}>{previewError}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Tab: Affected Files Terminal Card */}
                {(detailTab === 'files' || detailTab === 'all') && result.affected_files?.length > 0 && (() => {
                  const filteredFiles = result.affected_files.filter(f =>
                    !fileFilter || f.path?.toLowerCase().includes(fileFilter.toLowerCase())
                  );
                  return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '11.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-dim)' }}>
                          Affected Files ({filteredFiles.length} of {result.affected_files.length})
                        </span>
                        {result.affected_files.length > 4 && (
                          <input
                            type="text"
                            placeholder="Filter files..."
                            value={fileFilter}
                            onChange={e => setFileFilter(e.target.value)}
                            style={{
                              background: 'rgba(0,0,0,0.3)',
                              border: '1px solid var(--border)',
                              borderRadius: '6px',
                              color: 'var(--text)',
                              fontSize: '11px',
                              padding: '4px 10px',
                              outline: 'none',
                              width: '160px'
                            }}
                          />
                        )}
                      </div>
                      <div style={{
                        maxHeight: detailTab === 'all' ? '240px' : '420px',
                        overflowY: 'auto',
                        background: 'rgba(0, 0, 0, 0.4)',
                        borderRadius: '8px',
                        padding: '10px 14px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '5px',
                        border: '1px solid var(--border)'
                      }}>
                        {filteredFiles.map((f, i) => (
                          <div key={i} style={{ fontSize: '12px', fontFamily: 'var(--mono)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '1px 6px',
                              borderRadius: '4px',
                              background: f.change_type === 'added' ? 'rgba(0, 255, 136, 0.1)' : f.change_type === 'deleted' ? 'rgba(255, 45, 85, 0.1)' : 'rgba(251, 191, 36, 0.1)',
                              color: f.change_type === 'added' ? 'var(--green)' : f.change_type === 'deleted' ? 'var(--red)' : 'var(--yellow)',
                            }}>
                              {f.change_type.toUpperCase()}
                            </span>
                            <span style={{ color: 'var(--text)', flex: 1, wordBreak: 'break-all' }}>{f.path}</span>
                            <span style={{ color: 'var(--text-faint)', fontSize: '11px', whiteSpace: 'nowrap' }}>{f.lines_changed} lines</span>
                          </div>
                        ))}
                        {filteredFiles.length === 0 && (
                          <div className="text-dim text-xs" style={{ padding: '8px 0', textAlign: 'center' }}>No matching files found.</div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* Tab: Downstream Impact / Blast Radius */}
                {(detailTab === 'services' || detailTab === 'all') && result.impacted_services?.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ fontSize: '11.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-dim)' }}>
                      Downstream Impact / Blast Radius ({result.impacted_services.length} services)
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '10px' }}>
                      {result.impacted_services.map(s => (
                        <div key={s} style={{
                          background: 'rgba(58, 134, 255, 0.08)',
                          border: '1px solid rgba(58, 134, 255, 0.2)',
                          borderRadius: '8px',
                          padding: '10px 14px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px'
                        }}>
                          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--cyan)', boxShadow: '0 0 8px var(--cyan)', flexShrink: 0 }}></span>
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {s}
                            </div>
                            <div style={{ fontSize: '10.5px', color: 'var(--cyan)' }}>
                              Blast-Radius Transit
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
