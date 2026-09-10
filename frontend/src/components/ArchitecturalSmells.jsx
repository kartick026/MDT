import { useEffect, useState, useMemo } from 'react';
import { getSmells } from '../api';

const ICONS = {
  'Circular Dependency': '↻',
  'God / Bottleneck Service': '⚡',
  'High Coupling': '⚯',
  'Single Point of Failure (SPOF)': '🎯',
  'Dependency Explosion': '💥',
  'Dead / Isolated Service': '☠',
  'API Instability': '⍻',
  'Shared Database': '🗄️',
  'Chatty Communication': '💬',
  'Missing Circuit Breaker': '🛡️',
  'Hub-and-Spoke Centralization': '🕸️',
};

const CATEGORIES = {
  'Circular Dependency': 'Topology',
  'God / Bottleneck Service': 'Coupling',
  'High Coupling': 'Coupling',
  'Single Point of Failure (SPOF)': 'Resilience',
  'Dependency Explosion': 'Topology',
  'Dead / Isolated Service': 'Hygiene',
  'API Instability': 'Contract',
  'Shared Database': 'Data Layer',
  'Chatty Communication': 'Network',
  'Missing Circuit Breaker': 'Resilience',
  'Hub-and-Spoke Centralization': 'Topology',
};

const REMEDIATION_HINTS = {
  'Circular Dependency': 'Break cycle by introducing asynchronous event pub/sub (Kafka/RabbitMQ) or inverted dependency facade.',
  'God / Bottleneck Service': 'Decompose service responsibilities, introduce an API Gateway caching layer, or horizontal auto-scaling.',
  'High Coupling': 'Extract shared domain models or implement an orchestration gateway to decouple point-to-point calls.',
  'Single Point of Failure (SPOF)': 'Deploy redundant replicas across multiple availability zones with automated health failover.',
  'Dependency Explosion': 'Consolidate excessive outgoing dependencies into focused aggregators or event-driven streams.',
  'Dead / Isolated Service': 'Audit service traffic; deprecate and remove orphan microservices to reduce infrastructure footprint.',
  'API Instability': 'Implement strict semantic API versioning (/v1, /v2) with backward-compatible deprecation grace periods.',
  'Shared Database': 'Isolate database instances per service (Database-per-Service pattern); share data via published domain events.',
  'Chatty Communication': 'Batch roundtrips using GraphQL or bulk REST endpoints to eliminate high-latency RPC ping-pong.',
  'Missing Circuit Breaker': 'Wrap synchronous downstream HTTP calls with resilience circuit breakers (Resilience4j / Polly / Istio).',
  'Hub-and-Spoke Centralization': 'Distribute routing logic using a decentralized service mesh (Envoy / Linkerd) to prevent single point collapse.',
};

const SEVERITY_COLORS = {
  CRITICAL: 'var(--red)',
  HIGH: 'var(--orange)',
  MEDIUM: 'var(--yellow)',
  LOW: 'var(--text-dim)',
};

export default function ArchitecturalSmells() {
  const [smells, setSmells] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [selectedSeverity, setSelectedSeverity] = useState('ALL');

  useEffect(() => {
    getSmells()
      .then(data => {
        setSmells(data);
        setError(null);
      })
      .catch(err => {
        console.error(err);
        setError('Failed to fetch architectural smells from backend.');
      })
      .finally(() => setLoading(false));
  }, []);

  const filteredSmells = useMemo(() => {
    return smells.filter(smell => {
      const type = smell.type || '';
      const sev = (smell.severity || 'LOW').toUpperCase();

      const matchesSearch =
        type.toLowerCase().includes(search.toLowerCase()) ||
        smell.description?.toLowerCase().includes(search.toLowerCase()) ||
        smell.services?.some(s => s.toLowerCase().includes(search.toLowerCase()));

      const matchesSeverity = selectedSeverity === 'ALL' || sev === selectedSeverity;

      return matchesSearch && matchesSeverity;
    });
  }, [smells, search, selectedSeverity]);

  const severityCounts = useMemo(() => {
    const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    smells.forEach(s => {
      const sev = (s.severity || 'LOW').toUpperCase();
      if (counts[sev] !== undefined) counts[sev]++;
    });
    return counts;
  }, [smells]);

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Running smell detection across 10 architectural patterns…</span></div>;
  if (error) return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  return (
    <div className="smells-container" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* Control / Filter Bar */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '14px',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '14px 18px',
      }}>
        {/* Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '240px', flex: '1 1 auto' }}>
          <span style={{ fontSize: '15px', color: 'var(--text-dim)' }}>🔍</span>
          <input
            type="text"
            placeholder="Search 10 architectural smells or services…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: '100%',
              background: 'rgba(0,0,0,0.3)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              color: 'var(--text)',
              fontSize: '13px',
              padding: '7px 12px',
              outline: 'none',
            }}
          />
        </div>

        {/* Severity Filter Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-dim)', marginRight: '4px' }}>Severity:</span>
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(sev => {
            const isActive = selectedSeverity === sev;
            const count = sev === 'ALL' ? smells.length : severityCounts[sev] || 0;
            return (
              <button
                key={sev}
                type="button"
                onClick={() => setSelectedSeverity(sev)}
                style={{
                  background: isActive ? 'rgba(0, 212, 255, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  border: `1px solid ${isActive ? 'var(--cyan)' : 'var(--border)'}`,
                  color: isActive ? 'var(--cyan)' : 'var(--text-dim)',
                  borderRadius: '14px',
                  padding: '4px 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {sev} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {filteredSmells.length === 0 ? (
        <div className="card state-empty">
          <p>
            {smells.length === 0
              ? 'No architectural smells detected in the current system graph. Excellent system hygiene!'
              : 'No smells match the active search and filter criteria.'}
          </p>
        </div>
      ) : (
        <div className="smells-grid">
          {filteredSmells.map((smell, idx) => {
            const sevUpper = smell.severity?.toUpperCase() || 'LOW';
            const color = SEVERITY_COLORS[sevUpper] || 'var(--cyan)';
            const category = CATEGORIES[smell.type] || 'Architecture';
            const hint = REMEDIATION_HINTS[smell.type];
            const confidence = typeof smell.confidence === 'number'
              ? `${Math.round(smell.confidence * 100)}%`
              : (smell.confidence ? String(smell.confidence).replace(/^./, c => c.toUpperCase()) : 'Rule-based');

            return (
              <div key={idx} className="smell-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div className="smell-icon-wrapper" style={{ '--icon-color': color }}>
                    <div className="smell-icon">{ICONS[smell.type] || '⚠'}</div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <span style={{
                      fontSize: '10px',
                      fontWeight: 600,
                      padding: '2px 7px',
                      borderRadius: '4px',
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-dim)',
                      textTransform: 'uppercase'
                    }}>
                      {category}
                    </span>
                    <span style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      background: sevUpper === 'CRITICAL' ? 'rgba(255,45,85,0.15)' : 'rgba(251,191,36,0.15)',
                      color: color,
                      border: `1px solid ${color}33`,
                    }}>
                      {sevUpper}
                    </span>
                  </div>
                </div>

                <div>
                  <h3 className="smell-title" style={{ margin: '0 0 4px 0', fontSize: '15px', color: 'var(--text)' }}>
                    {smell.type}
                  </h3>
                  <p className="smell-desc" style={{ margin: 0, fontSize: '12.5px', lineHeight: 1.5 }}>
                    {smell.description}
                  </p>
                </div>

                {hint && (
                  <div style={{
                    background: 'rgba(0, 212, 255, 0.04)',
                    borderLeft: '3px solid var(--cyan)',
                    padding: '8px 10px',
                    borderRadius: '0 6px 6px 0',
                    fontSize: '11.5px',
                    color: 'var(--text-dim)',
                    lineHeight: 1.4,
                  }}>
                    <strong style={{ color: 'var(--cyan)' }}>Fix: </strong>
                    {hint}
                  </div>
                )}

                <div className="smell-meta" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '6px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Confidence: <strong style={{ color: 'var(--cyan)' }}>{confidence}</strong>
                  </span>
                </div>

                {smell.services?.length > 0 && (
                  <div className="smell-services" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {smell.services.map(s => (
                      <span key={s} className="tag text-xs" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)' }}>
                        {s.replace('-service', '')}
                      </span>
                    ))}
                  </div>
                )}

                {smell.evidence && (
                  <details className="smell-evidence">
                    <summary style={{ fontSize: '11px', color: 'var(--text-dim)', cursor: 'pointer' }}>View detection evidence</summary>
                    <pre style={{ fontSize: '11px', maxHeight: '160px', overflowY: 'auto', background: 'rgba(0,0,0,0.5)', padding: '8px', borderRadius: '6px' }}>
                      {JSON.stringify(smell.evidence, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
