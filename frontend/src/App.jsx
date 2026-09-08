import { useState, useEffect, useRef } from 'react';
import ServiceGrid from './components/ServiceGrid';
import ImpactForm from './components/ImpactForm';
import DependencyGraph from './components/DependencyGraph';
import AnalysisHistory from './components/AnalysisHistory';
import ArchitecturalSmells from './components/ArchitecturalSmells';
import { getServices, getHealth } from './api';
import './App.css';

const TABS = [
  { id: 'overview',  label: 'Overview',         icon: '◈' },
  { id: 'impact',    label: 'Impact Analysis',   icon: '⚡' },
  { id: 'graph',     label: 'Dependency Graph',  icon: '⬡' },
  { id: 'smells',    label: 'Architectural Smells', icon: '⚠' },
  { id: 'history',   label: 'Analysis History',  icon: '≡' },
];

function AnimatedNumber({ target, duration = 1200 }) {
  const [val, setVal] = useState(0);
  const startRef = useRef(null);
  useEffect(() => {
    startRef.current = performance.now();
    const tick = (now) => {
      const elapsed = now - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      setVal(Math.round(ease * target));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [target, duration]);
  return <>{val}</>;
}

export default function App() {
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState({ total: 4, healthy: 0, analyses: 0, avgRisk: 0, scoreCount: 0 });
  const [sysHealth, setSysHealth] = useState({ state: 'loading', label: '… Connecting' });
  const [detailedHealth, setDetailedHealth] = useState(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const services = await getServices();
        const healthDetails = await getHealth();
        setDetailedHealth(healthDetails);
        
        const healthy = services.filter(s => s.status === 'healthy').length;
        const total = services.length;
        const scores = services.map(s => s.risk_score).filter(Boolean);
        const avgRisk = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
        
        let healthState = 'healthy';
        let label = '● All Systems Go';

        if (healthDetails?.status !== 'healthy') {
          healthState = 'offline';
          label = '✕ Backend Offline';
        } else if (total > 0 && healthy === 0) {
          healthState = 'idle';
          label = `○ ${total} Services Imported (Offline)`;
        } else if (healthy < total) {
          healthState = 'degraded';
          label = `◐ ${healthy}/${total} Services Online`;
        } else {
          healthState = 'healthy';
          label = `● All ${total} Services Online`;
        }

        setSysHealth({ state: healthState, label });
        setStats(s => ({ ...s, total, healthy, avgRisk, scoreCount: scores.length }));
      } catch {
        setSysHealth({ state: 'offline', label: '✕ Backend Offline' });
      }
    };
    poll();
    const id = setInterval(poll, 6000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="app">
      {/* ── Navbar ── */}
      <nav className="navbar">
        <div className="nav-brand">
          <div className="nav-logo">M</div>
          <div>
            <div className="nav-name">MDT</div>
            <div className="nav-sub">Drift Tracker</div>
          </div>
        </div>

        <div className="nav-tabs">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`nav-tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span className="nav-tab-icon">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>

        <div className="nav-right">
          <div className={`health-badge ${sysHealth.state || 'loading'}`} title="Operational Service Status">
            <span className="health-dot" />
            {sysHealth.label}
          </div>
          <span className="api-chip">:8000</span>
        </div>
      </nav>

      {/* ── Page ── */}
      <div className="page">
        {tab === 'overview' && (
          <div className="anim-fade-up">
            <h1 className="page-title">Service Overview</h1>
            <p className="page-sub">Live health and risk status of all microservices — refreshes every 5 seconds</p>

            {/* Stats Bar */}
            <div className="stats-bar">
              <div className="stat-card" style={{'--accent': 'var(--cyan)'}}>
                <div className="stat-label">Total Services</div>
                <div className="stat-value"><AnimatedNumber target={stats.total} /></div>
                <div className="stat-delta text-dim text-xs">across all environments</div>
              </div>
              <div className="stat-card" style={{'--accent': 'var(--green)'}}>
                <div className="stat-label">Healthy</div>
                <div className="stat-value" style={{color:'var(--green)'}}>
                  <AnimatedNumber target={stats.healthy} />
                </div>
                <div className="stat-delta text-dim text-xs">services online</div>
              </div>
              <div className="stat-card" style={{'--accent': 'var(--purple)'}}>
                <div className="stat-label">Analyses Run</div>
                <div className="stat-value" style={{color:'var(--purple)'}}>
                  <AnimatedNumber target={stats.analyses} />
                </div>
                <div className="stat-delta text-dim text-xs">this session</div>
              </div>
              <div className="stat-card" style={{'--accent': stats.analyses === 0 && stats.scoreCount === 0 ? 'var(--text-dim)' : stats.avgRisk > 60 ? 'var(--red)' : stats.avgRisk > 30 ? 'var(--yellow)' : 'var(--green)'}}>
                <div className="stat-label">Avg Drift Risk</div>
                <div className="stat-value" style={{color: stats.analyses === 0 && stats.scoreCount === 0 ? 'var(--text-dim)' : stats.avgRisk > 60 ? 'var(--red)' : stats.avgRisk > 30 ? 'var(--yellow)' : 'var(--green)'}}>
                  {stats.analyses === 0 && stats.scoreCount === 0 ? '0' : <AnimatedNumber target={stats.avgRisk} />}
                </div>
                <div className="stat-delta text-dim text-xs">
                  {stats.analyses === 0 && stats.scoreCount === 0 ? 'No drift analyzed yet' : 'out of 100'}
                </div>
              </div>
            </div>

            {detailedHealth && (
              <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem', marginBottom: '2rem' }}>
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.5rem 1rem', borderRadius: '4px', fontSize: '0.85rem' }}>
                  <span style={{ color: 'var(--text-dim)', marginRight: '0.5rem' }}>Neo4j Graph:</span>
                  <span style={{ color: detailedHealth.components?.neo4j === 'connected' ? 'var(--green)' : 'var(--yellow)' }}>
                    {detailedHealth.components?.neo4j === 'connected' ? 'Connected' : 'Disabled (Fallback mode)'}
                  </span>
                </div>
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.5rem 1rem', borderRadius: '4px', fontSize: '0.85rem' }}>
                  <span style={{ color: 'var(--text-dim)', marginRight: '0.5rem' }}>ChromaDB Retrieval:</span>
                  <span style={{ color: detailedHealth.components?.chroma === 'connected' ? 'var(--green)' : 'var(--yellow)' }}>
                    {detailedHealth.components?.chroma === 'connected' ? 'Connected' : 'Disabled (Fallback mode)'}
                  </span>
                </div>
              </div>
            )}

            <ServiceGrid onAnalysis={(count) => setStats(s => ({...s, analyses: s.analyses + count}))} />
          </div>
        )}

        {tab === 'impact' && (
          <div className="anim-fade-up">
            <h1 className="page-title">Impact Analysis</h1>
            <p className="page-sub">Paste a git diff to run HMDA risk scoring — results appear live on the right</p>
            <ImpactForm onAnalysis={() => setStats(s => ({...s, analyses: s.analyses + 1}))} />
          </div>
        )}

        {tab === 'graph' && (
          <div className="anim-fade-up">
            <h1 className="page-title">Dependency Graph</h1>
            <p className="page-sub">Live graph of cross-service dependencies, coloured by risk level</p>
            <DependencyGraph />
          </div>
        )}

        {tab === 'history' && (
          <div className="anim-fade-up">
            <h1 className="page-title">Analysis History</h1>
            <p className="page-sub">All HMDA analyses run this session — auto-refreshes every 8 seconds</p>
            <AnalysisHistory />
          </div>
        )}

        {tab === 'smells' && (
          <div className="anim-fade-up">
            <h1 className="page-title">Architectural Smells Detected</h1>
            <p className="page-sub">DETECTION — Heuristic and Cypher analysis of structural risks</p>
            <ArchitecturalSmells />
          </div>
        )}
      </div>
    </div>
  );
}
