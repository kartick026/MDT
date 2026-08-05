import { useEffect, useState, useCallback } from 'react';
import { getServices } from '../api';

const RISK_COLOR = {
  LOW:      'var(--green)',
  MEDIUM:   'var(--yellow)',
  HIGH:     'var(--orange)',
  CRITICAL: 'var(--red)',
  UNKNOWN:  'var(--text-faint)',
};

function RiskBar({ score, level }) {
  const color = RISK_COLOR[level] || RISK_COLOR.UNKNOWN;
  return (
    <div className="risk-bar-track">
      <div className="risk-bar-fill" style={{ width: `${score || 0}%`, background: color }} />
    </div>
  );
}

export default function ServiceGrid() {
  const [services, setServices] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing]   = useState(false);

  const fetchServices = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const data = await getServices();
      setServices(data);
      setLastUpdated(new Date());
      setError(null);
    } catch {
      setError("Cannot reach MDT backend. Make sure Docker is running on :8000");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchServices();
    const id = setInterval(fetchServices, 5000);
    return () => clearInterval(id);
  }, [fetchServices]);

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Polling services…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  if (!services.length) {
    return (
      <div className="card state-empty">
        <p>No services registered yet. The backend is online but the graph is empty.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="refresh-row">
        <span className="text-dim text-xs">
          Auto-refreshing every 5s
          {lastUpdated && ` · Updated ${lastUpdated.toLocaleTimeString()}`}
        </span>
        <button className="btn btn-ghost" onClick={() => fetchServices(true)} disabled={refreshing}>
          {refreshing ? <span className="spinner-xs" /> : '↻'} Refresh
        </button>
      </div>

      <div className="service-grid">
        {services.map(svc => {
          const riskLevel = (svc.risk_level || 'UNKNOWN').toUpperCase();
          const riskColor = RISK_COLOR[riskLevel] || RISK_COLOR.UNKNOWN;
          const deps = Array.isArray(svc.dependencies) ? svc.dependencies : [];
          const status = svc.status || 'unknown';

          return (
            <div key={svc.name} className="service-card" data-risk={riskLevel}>
              <div className="svc-header">
                <div>
                  <div className="svc-title">{svc.display_name || svc.name}</div>
                  <div className="svc-port text-mono text-xs text-dim">:{svc.port || '—'}</div>
                </div>
                <div
                  className={`svc-status-dot ${status === 'healthy' ? 'healthy' : status === 'offline' ? 'offline' : ''}`}
                  title={status}
                />
              </div>

              <div className="svc-badges">
                <span className="tag text-xs" style={{
                  color: status === 'healthy' ? 'var(--green)' : 'var(--text-dim)',
                  borderColor: status === 'healthy' ? 'rgba(0,255,136,.3)' : 'rgba(255,255,255,.1)',
                  background: status === 'healthy' ? 'var(--green-dim)' : 'rgba(255,255,255,0.04)',
                }}>
                  {status}
                </span>
                <span className="tag text-xs" style={{
                  color: riskColor,
                  borderColor: `${riskColor}44`,
                  background: `${riskColor}14`,
                }}>
                  {riskLevel}
                </span>
              </div>

              <RiskBar score={svc.risk_score} level={riskLevel} />

              <div className="svc-footer">
                <span>{svc.api_count || 0} endpoints</span>
                {deps.length > 0 && (
                  <span>↑ {deps.map(d => d.replace('_service', '')).join(', ')}</span>
                )}
                {svc.description && (
                  <span className="text-dim" style={{ fontSize: '11px', marginTop: '4px' }}>
                    {svc.description}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
