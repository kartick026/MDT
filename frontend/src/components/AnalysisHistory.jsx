import { useEffect, useState } from 'react';
import { getHistory } from '../api';

const RISK_COLORS = {
  LOW: 'var(--green)', MEDIUM: 'var(--yellow)', HIGH: 'var(--orange)', CRITICAL: 'var(--red)',
};
const RISK_ICONS = { LOW: '🟢', MEDIUM: '🟡', HIGH: '🟠', CRITICAL: '🔴' };

export default function AnalysisHistory() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [expanded, setExpanded] = useState(null);

  const loadHistory = async () => {
    try {
      const data = await getHistory();
      setHistory(data);
      setError(null);
    } catch {
      setError('Could not reach backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
    const id = setInterval(loadHistory, 8000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Loading history…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  if (!history.length) {
    return (
      <div className="card state-empty">
        <p>No analyses yet — run one in the <strong>Impact Analysis</strong> tab.</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <span className="text-dim text-xs">{history.length} analyses · auto-refreshing every 8s</span>
      </div>

      <div className="history-list">
        {history.map((item, i) => {
          const score  = item.risk_score ?? 0;
          let level  = (item.risk_level || item.severity || 'LOW').toUpperCase();
          if (item.risk_score != null) {
            if (item.risk_score >= 75) level = 'CRITICAL';
            else if (item.risk_score >= 50) level = 'HIGH';
            else if (item.risk_score >= 25) level = 'MEDIUM';
            else level = 'LOW';
          }
          const color  = RISK_COLORS[level] || 'var(--text-faint)';
          const icon   = RISK_ICONS[level]  || '⚪';
          const repoName = item.repo_url
            ? item.repo_url.replace(/\.git$/i, '').split('/').slice(-2).join('/')
            : (item.service && item.service !== 'backend' && item.service !== 'unknown'
                ? item.service.replace(/_/g, ' ')
                : 'kartick026/MDT');
          const rawCommit = item.commit_sha || item.commit || '';
          const commitRef = rawCommit.length >= 7 ? rawCommit.substring(0, 7) : rawCommit;
          const branchRef = item.branch_ref || null;
          const open   = expanded === i;

          return (
            <div key={i} className="h-card">
              <div className="h-row" onClick={() => setExpanded(open ? null : i)}>
                <span className="h-score-badge" style={{ color }}>{score}</span>
                <span className="h-service" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                  <span>{repoName}</span>
                  {branchRef && <span className="text-dim text-xs" style={{ opacity: 0.7 }}>@{branchRef}</span>}
                  {commitRef && <span className="text-mono text-xs" style={{ color: 'var(--cyan)', background: 'rgba(0, 212, 255, 0.08)', padding: '1px 6px', borderRadius: '4px' }} title={`Commit SHA: ${rawCommit}`}>{commitRef}</span>}
                  {item.triggered_by && <span className="text-dim text-xs" style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 6px', borderRadius: '4px', border: '1px solid var(--border)' }}>👤 {item.triggered_by}</span>}
                </span>
                <span className="h-level" style={{ color }}>{icon} {level}</span>
                <span className="h-time">
                  {item.timestamp
                    ? new Date(item.timestamp).toLocaleTimeString()
                    : '—'}
                </span>
                <span className="h-chevron">{open ? '▲' : '▼'}</span>
              </div>

              {open && (
                <div className="h-body anim-fade-in">
                  {item.explanation && (
                    <p className="h-explain">{item.explanation.replace(/\*\*/g, '')}</p>
                  )}

                  {item.downstream_services?.length > 0 && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10, alignItems: 'center' }}>
                      <span className="text-xs text-dim">Affected Services:</span>
                      {item.downstream_services.map(s => (
                        <span key={s} className="dtag">{s.replace('-service', '').replace('_service', '')}</span>
                      ))}
                    </div>
                  )}

                  {item.affected_files?.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span className="text-xs text-dim" style={{ fontWeight: 600 }}>Affected Files ({item.affected_files.length}):</span>
                      </div>
                      <div style={{
                        maxHeight: '160px',
                        overflowY: 'auto',
                        background: 'rgba(0,0,0,0.3)',
                        borderRadius: '6px',
                        padding: '8px 12px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                        border: '1px solid var(--border)'
                      }}>
                        {item.affected_files.map((f, fi) => (
                          <div key={fi} className="text-xs text-mono" style={{ color: '#7ee787', lineHeight: '1.4' }}>
                            {typeof f === 'string' ? f : f.path}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="h-chips">
                    {Object.entries(item.score_breakdown || {}).map(([k, v]) => (
                      <span key={k} className="h-chip">
                        {k.replace(/_/g, ' ')}: <strong>{v}</strong>
                      </span>
                    ))}
                    {item.confidence != null && (
                      <span className="h-chip">
                        confidence: <strong>{(item.confidence * 100).toFixed(0)}%</strong>
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
