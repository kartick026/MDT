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
          const level  = (item.risk_level || item.severity || 'UNKNOWN').toUpperCase();
          const color  = RISK_COLORS[level] || 'var(--text-faint)';
          const icon   = RISK_ICONS[level]  || '⚪';
          const score  = item.risk_score ?? 0;
          const svc    = (item.service || item.impacted_services?.[0] || 'unknown').replace(/_/g, ' ');
          const open   = expanded === i;

          return (
            <div key={i} className="h-card">
              <div className="h-row" onClick={() => setExpanded(open ? null : i)}>
                <span className="h-score-badge" style={{ color }}>{score}</span>
                <span className="h-service">{svc}</span>
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
                      <span className="text-xs text-dim">Affected:</span>
                      {item.downstream_services.map(s => (
                        <span key={s} className="dtag">{s.replace('-service', '').replace('_service', '')}</span>
                      ))}
                    </div>
                  )}

                  {item.affected_files?.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <span className="text-xs text-dim">Files changed: </span>
                      {item.affected_files.map((f, fi) => (
                        <span key={fi} className="h-chip" style={{ marginLeft: 4 }}>
                          {typeof f === 'string' ? f : f.path}
                        </span>
                      ))}
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
