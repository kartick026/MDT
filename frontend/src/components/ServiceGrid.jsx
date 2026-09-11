import { useEffect, useState, useCallback } from 'react';
import { getServices, importRepo, getConnectionBugs, resetDefaultRegistry } from '../api';
import { useAuth } from '../context/AuthContext';
import { useToast } from './Toast';

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

// In-memory cache for instant tab transitions without spinner flashes (stale-while-revalidate)
let cachedServices = null;
let cachedBugs = null;
let cachedLastUpdated = null;

export default function ServiceGrid({ onImportSuccess, onNavigateTab }) {
  const { isAuthenticated, openLoginModal } = useAuth();
  const { addToast } = useToast();

  const [services, setServices] = useState(() => cachedServices || []);
  const [loading, setLoading]   = useState(() => !cachedServices);
  const [error, setError]       = useState(null);
  const [lastUpdated, setLastUpdated] = useState(() => cachedLastUpdated || null);
  const [refreshing, setRefreshing]   = useState(false);
  const [resetting, setResetting]     = useState(false);

  // Import Repo state
  const [showImport, setShowImport]     = useState(false);
  const [importUrl, setImportUrl]       = useState('https://github.com/kartick026/MDT');
  const [importBranch, setImportBranch] = useState('main');
  const [importing, setImporting]       = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Connection bugs state
  const [bugs, setBugs] = useState(() => cachedBugs || []);

  const fetchServices = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const [svcData, bugData] = await Promise.all([
        getServices(),
        getConnectionBugs().catch(() => [])
      ]);
      cachedServices = svcData;
      cachedBugs = bugData;
      cachedLastUpdated = new Date();
      setServices(svcData);
      setBugs(bugData);
      setLastUpdated(cachedLastUpdated);
      setError(null);
    } catch {
      if (!cachedServices) {
        setError("Cannot reach MDT backend. Make sure Docker is running on :8000");
      }
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

  const handleResetFleet = async () => {
    if (!isAuthenticated) {
      addToast("Authentication required: Sign in as administrator to reset the service registry.", "warning");
      openLoginModal();
      return;
    }
    setResetting(true);
    try {
      await resetDefaultRegistry();
      addToast("Local demo fleet restored successfully!", "success");
      onImportSuccess?.({ repo_url: 'https://github.com/kartick026/MDT', branch: 'main' });
      await fetchServices(true);
    } catch (err) {
      const msg = err.response?.status === 404
        ? "Reset registry endpoint not found (404)."
        : (err.response?.data?.detail || "Failed to reset fleet.");
      addToast(msg, "error");
      console.error("Failed to reset fleet:", err);
    } finally {
      setResetting(false);
    }
  };

  const handleImport = async (e) => {
    e.preventDefault();
    if (!isAuthenticated) {
      addToast("Authentication required: Sign in as administrator to import repositories.", "warning");
      openLoginModal();
      return;
    }
    if (!importUrl) return;
    setImporting(true);
    setImportResult(null);
    try {
      const targetBranch = (importBranch || '').trim() || 'main';
      const res = await importRepo({ repo_url: importUrl.trim(), branch: targetBranch });
      addToast(`Imported ${res.services_count} services and ${res.dependencies_count} dependencies from branch "${targetBranch}"!`, "success");
      setImportResult({
        success: true,
        message: `Successfully imported ${res.services_count} services and ${res.dependencies_count} dependencies from ${res.compose_file || 'repo'} (${targetBranch})!`,
        bugsCount: res.connection_bugs?.length || 0,
        branch: targetBranch,
      });
      onImportSuccess?.({
        repo_url: importUrl.trim(),
        branch: targetBranch,
        ...res
      });
      await fetchServices(true);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Import failed.';
      addToast(msg, "error");
      setImportResult({
        success: false,
        message: msg
      });
      await fetchServices(true);
    } finally {
      setImporting(false);
    }
  };

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Polling services…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  const isImportedOffline = services.length > 0 && services.every(s => s.status === 'offline' || s.status === 'unknown');

  return (
    <div>
      {/* Top action row */}
      <div className="refresh-row">
        <span className="text-dim text-xs">
          Auto-refreshing every 6s
          {lastUpdated && ` · Updated ${lastUpdated.toLocaleTimeString()}`}
        </span>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            className="btn btn-ghost"
            onClick={handleResetFleet}
            disabled={resetting}
            title={isAuthenticated ? "Switch back to live local Docker services (:8001-:8004)" : "Sign in required to restore fleet"}
            style={{ color: 'var(--cyan)' }}
          >
            {resetting ? <span className="spinner-xs" /> : '↺'} {!isAuthenticated && '🔒 '}Restore Local Demo Fleet
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => {
              if (!isAuthenticated) {
                addToast("Authentication required: Sign in as administrator to import repositories.", "warning");
                openLoginModal();
                return;
              }
              setShowImport(!showImport);
            }}
            title={isAuthenticated ? "Import architecture from a GitHub repo" : "Sign in required to import repository"}
          >
            {showImport ? '✕ Close Import' : (!isAuthenticated ? '🔒 📁 Import Repository' : '📁 Import Repository')}
          </button>
          <button className="btn btn-ghost" onClick={() => fetchServices(true)} disabled={refreshing}>
            {refreshing ? <span className="spinner-xs" /> : '↻'} Refresh
          </button>
        </div>
      </div>

      {/* Notice when services are imported from external repo and thus offline */}
      {isImportedOffline && (
        <div style={{
          background: 'rgba(58, 134, 255, 0.08)',
          border: '1px solid rgba(58, 134, 255, 0.3)',
          borderRadius: '8px',
          padding: '14px 18px',
          marginBottom: '20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap'
        }}>
          <div style={{ flex: '1 1 320px' }}>
            <div style={{ color: 'var(--blue)', fontWeight: 600, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>ℹ</span> External Repository Architecture Mode
            </div>
            <p className="text-dim text-xs" style={{ marginTop: '4px', lineHeight: '1.4' }}>
              You are currently viewing architecture imported from an external repository. These services are modeled in Neo4j for drift & blast-radius analysis; their actual containers are not running on local Docker.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleResetFleet}
            disabled={resetting}
            style={{ fontSize: '12px', padding: '6px 14px', whiteSpace: 'nowrap' }}
          >
            {resetting ? <><span className="spinner-xs" /> Restoring…</> : '↺ Restore Local Demo Fleet (:8001-:8004)'}
          </button>
        </div>
      )}

      {/* Import Repository Drawer / Panel */}
      {showImport && (
        <div className="card" style={{ marginBottom: '24px', padding: '20px', border: '1px solid var(--border-md)' }}>
          <div style={{ fontWeight: '600', fontSize: '15px', marginBottom: '4px' }}>
            Auto-Discover Architecture from GitHub
          </div>
          <p className="text-dim text-xs" style={{ marginBottom: '16px' }}>
            Enter any GitHub repository URL. MDT will scan <code>docker-compose.yml</code> or automatically infer services from the directory structure, map dependencies, and validate inter-service API contracts.
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
              padding: '12px 14px',
              borderRadius: '6px',
              fontSize: '13px',
              background: importResult.success ? 'var(--green-dim)' : 'var(--red-dim)',
              color: importResult.success ? 'var(--green)' : 'var(--red)',
              border: `1px solid ${importResult.success ? 'rgba(0,255,136,0.2)' : 'rgba(255,45,85,0.2)'}`
            }}>
              <div>{importResult.message}</div>
              {!importResult.success && importResult.message.includes("Did you mean '") && (
                <div style={{ marginTop: '8px' }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => {
                      const m = importResult.message.match(/Did you mean '([^']+)'\?/);
                      if (m && m[1]) {
                        setImportBranch(m[1]);
                        setImportResult(null);
                      }
                    }}
                    style={{ fontSize: '12px', padding: '4px 10px', color: 'var(--cyan)', border: '1px solid rgba(0, 212, 255, 0.4)', background: 'rgba(0, 212, 255, 0.08)' }}
                  >
                    Use suggested branch: {importResult.message.match(/Did you mean '([^']+)'\?/)?.[1]} ↵
                  </button>
                </div>
              )}
              {importResult.bugsCount > 0 && (
                <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.9 }}>
                  ⚠ {importResult.bugsCount} architectural connection issue(s) detected.
                </div>
              )}
              {importResult.success && onNavigateTab && (
                <div style={{ marginTop: '10px' }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onNavigateTab('impact')}
                    style={{ fontSize: '12px', padding: '6px 14px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    <span>⚡ Run Impact Analysis on {importResult.branch || 'branch'}</span>
                    <span>➔</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Connection Bugs Banner — Clarified as Architectural Defect Discovered by MDT */}
      {bugs.length > 0 && (
        <div style={{
          background: 'rgba(255, 45, 85, 0.07)',
          border: '1px solid rgba(255, 45, 85, 0.35)',
          borderRadius: '8px',
          padding: '16px 20px',
          marginBottom: '24px',
          boxShadow: '0 4px 20px rgba(255, 45, 85, 0.08)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ color: 'var(--red)', fontWeight: 'bold', fontSize: '13.5px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>⚡</span> Architectural Contract Defect Detected in Repository Code ({bugs.length})
            </div>
            <span style={{
              fontSize: '11px',
              fontFamily: 'var(--mono)',
              padding: '2px 8px',
              borderRadius: '4px',
              background: 'rgba(255, 45, 85, 0.15)',
              color: 'var(--red)',
              fontWeight: 600
            }}>
              IMPACTS RISK SCORE
            </span>
          </div>
          <p className="text-dim text-xs" style={{ margin: '6px 0 10px 0' }}>
            MDT static code analysis scanned inter-service API contracts and detected runtime routing failure risks in this repository:
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {bugs.map((b, idx) => (
              <div key={idx} style={{
                fontSize: '12.5px',
                lineHeight: '1.45',
                padding: '8px 12px',
                borderRadius: '6px',
                background: 'rgba(0, 0, 0, 0.25)',
                border: '1px solid rgba(255, 255, 255, 0.05)'
              }}>
                <strong style={{ color: 'var(--red)' }}>[{b.bug_type}]</strong> {b.description}
                <div style={{ marginTop: '4px', color: 'var(--cyan)', fontSize: '12px' }}>
                  <strong>💡 Suggested Remediation:</strong> {b.suggestion}
                </div>
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
            const riskLabel = riskLevel === 'UNKNOWN' ? 'NOT ANALYZED' : riskLevel;
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
                    className={`svc-status-dot ${status === 'healthy' ? 'healthy' : status === 'imported' ? 'imported' : status === 'offline' ? 'offline' : ''}`}
                    title={status === 'imported' ? 'Imported Architecture Model (Ready for Impact Analysis)' : status}
                  />
                </div>

                <div className="svc-badges">
                  <span className="tag text-xs" style={{
                    color: status === 'healthy' ? 'var(--green)' : status === 'imported' ? 'var(--cyan)' : 'var(--text-dim)',
                    borderColor: status === 'healthy' ? 'rgba(0,255,136,.3)' : status === 'imported' ? 'rgba(0,212,255,.3)' : 'rgba(255,255,255,.1)',
                    background: status === 'healthy' ? 'var(--green-dim)' : status === 'imported' ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.04)',
                  }}>
                    {status}
                  </span>
                  <span className="tag text-xs" style={{
                    color: riskColor,
                    borderColor: `${riskColor}44`,
                    background: `${riskColor}14`,
                  }}>
                    {riskLabel}
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
