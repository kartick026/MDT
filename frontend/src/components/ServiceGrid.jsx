import { useEffect, useState, useCallback } from 'react';
import { getServices, importRepo, getConnectionBugs } from '../api';

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

  // Import Repo state
  const [showImport, setShowImport]     = useState(false);
  const [importUrl, setImportUrl]       = useState('https://github.com/kartick026/MDT');
  const [importBranch, setImportBranch] = useState('main');
  const [importing, setImporting]       = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Connection bugs state
  const [bugs, setBugs] = useState([]);

  const fetchServices = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const [svcData, bugData] = await Promise.all([
        getServices(),
        getConnectionBugs().catch(() => [])
      ]);
      setServices(svcData);
      setBugs(bugData);
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
    const id = setInterval(fetchServices, 6000);
    return () => clearInterval(id);
  }, [fetchServices]);

  const handleImport = async (e) => {
    e.preventDefault();
    if (!importUrl) return;
    setImporting(true);
    setImportResult(null);
    try {
      const res = await importRepo({ repo_url: importUrl, branch: importBranch });
      setImportResult({
        success: true,
        message: `Successfully imported ${res.services_count} services and ${res.dependencies_count} dependencies from ${res.compose_file || 'repo'}!`,
        bugsCount: res.connection_bugs?.length || 0
      });
      await fetchServices(true);
    } catch (err) {
      setImportResult({
        success: false,
        message: err.response?.data?.detail || err.message || 'Import failed.'
      });
      await fetchServices(true);
    } finally {
      setImporting(false);
    }
  };

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Polling services…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  return (
    <div>
      {/* Top action row */}
      <div className="refresh-row">
        <span className="text-dim text-xs">
          Auto-refreshing every 6s
          {lastUpdated && ` · Updated ${lastUpdated.toLocaleTimeString()}`}
        </span>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-ghost" onClick={() => setShowImport(!showImport)}>
            {showImport ? '✕ Close Import' : '📁 Import Repository'}
          </button>
          <button className="btn btn-ghost" onClick={() => fetchServices(true)} disabled={refreshing}>
            {refreshing ? <span className="spinner-xs" /> : '↻'} Refresh
          </button>
        </div>
      </div>

      {/* Import Repository Drawer / Panel */}
      {showImport && (
        <div className="card" style={{ marginBottom: '24px', padding: '20px', border: '1px solid var(--border-md)' }}>
          <div style={{ fontWeight: '600', fontSize: '15px', marginBottom: '4px' }}>
            Auto-Discover Architecture from GitHub
          </div>
          <p className="text-dim text-xs" style={{ marginBottom: '16px' }}>
            Enter any GitHub repository URL. MDT will scan its <code>docker-compose.yml</code> to auto-register microservices, map dependencies, and run connection checks.
          </p>
          <form onSubmit={handleImport} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 300px' }}>
              <label className="form-label">Repository URL</label>
              <input
                type="text"
                className="form-input"
                placeholder="https://github.com/owner/repo"
                value={importUrl}
                onChange={e => setImportUrl(e.target.value)}
                required
              />
            </div>
            <div style={{ width: '120px' }}>
              <label className="form-label">Branch</label>
              <input
                type="text"
                className="form-input"
                placeholder="main"
                value={importBranch}
                onChange={e => setImportBranch(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={importing} style={{ height: '42px' }}>
              {importing ? <><span className="spinner-xs" /> Importing…</> : '🚀 Ingest Architecture'}
            </button>
          </form>

          {importResult && (
            <div style={{
              marginTop: '12px',
              padding: '10px 14px',
              borderRadius: '6px',
              fontSize: '13px',
              background: importResult.success ? 'var(--green-dim)' : 'var(--red-dim)',
              color: importResult.success ? 'var(--green)' : 'var(--red)',
              border: `1px solid ${importResult.success ? 'rgba(0,255,136,0.2)' : 'rgba(255,45,85,0.2)'}`
            }}>
              {importResult.message}
              {importResult.bugsCount > 0 && ` (${importResult.bugsCount} connection issue(s) detected)`}
            </div>
          )}
        </div>
      )}

      {/* Connection Bugs Banner */}
      {bugs.length > 0 && (
        <div style={{
          background: 'rgba(255, 45, 85, 0.08)',
          border: '1px solid rgba(255, 45, 85, 0.3)',
          borderRadius: '8px',
          padding: '14px 18px',
          marginBottom: '24px'
        }}>
          <div style={{ color: 'var(--red)', fontWeight: 'bold', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>⚠</span> Connection Integrity Issues ({bugs.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
            {bugs.map((b, idx) => (
              <div key={idx} style={{ fontSize: '12px', lineHeight: '1.4' }}>
                <strong style={{ color: 'var(--red)' }}>[{b.bug_type}]</strong> {b.description}
                <span className="text-dim" style={{ marginLeft: '6px' }}>— {b.suggestion}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!services.length ? (
        <div className="card state-empty">
          <p>No services registered yet. Click "Import Repository" above to discover services from a GitHub repository.</p>
        </div>
      ) : (
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

                <div className="svc-footer" style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: 'auto' }}>
                  <div className="svc-footer-meta" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '5px',
                      fontSize: '11px',
                      fontFamily: 'var(--mono)',
                      color: 'var(--cyan)',
                      background: 'rgba(0, 212, 255, 0.08)',
                      border: '1px solid rgba(0, 212, 255, 0.25)',
                      padding: '3px 8px',
                      borderRadius: '5px',
                      fontWeight: 600,
                      whiteSpace: 'nowrap'
                    }}>
                      <span>🔌</span> {svc.api_count || 0} endpoints
                    </span>

                    {deps.length > 0 ? (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '11px',
                        color: 'var(--text-dim)',
                        background: 'rgba(255, 255, 255, 0.04)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        padding: '3px 8px',
                        borderRadius: '5px',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        maxWidth: '150px'
                      }} title={`Depends on: ${deps.join(', ')}`}>
                        <span style={{ color: 'var(--cyan)' }}>↑</span> {deps.map(d => d.replace(/[-_]service/g, '')).join(', ')}
                      </span>
                    ) : (
                      <span style={{ fontSize: '11px', color: 'var(--text-faint)' }}>Independent</span>
                    )}
                  </div>

                  {svc.description && (
                    <div className="svc-desc" style={{
                      fontSize: '11.5px',
                      lineHeight: '1.45',
                      color: 'var(--text-dim)',
                      borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                      paddingTop: '8px',
                      marginTop: '2px'
                    }}>
                      {svc.description}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
