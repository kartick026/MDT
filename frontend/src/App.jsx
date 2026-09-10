import { useState, useEffect, useRef } from 'react';
import ServiceGrid from './components/ServiceGrid';
import ImpactForm from './components/ImpactForm';
import DependencyGraph from './components/DependencyGraph';
import AnalysisHistory from './components/AnalysisHistory';
import ArchitecturalSmells from './components/ArchitecturalSmells';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginModal from './components/LoginModal';
import SystemHealthModal from './components/SystemHealthModal';
import AuthPage from './components/AuthPage';
import { getServices, getHealth, getHistory } from './api';
import './App.css';




function AnimatedNumber({ target, duration = 1200 }) {
  const [val, setVal] = useState(0);
  const startRef = useRef(null);
  useEffect(() => {
    let frameId;
    startRef.current = performance.now();
    const tick = (now) => {
      const elapsed = now - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      setVal(Math.round(ease * target));
      if (progress < 1) frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [target, duration]);
  return <>{val}</>;
}

function MainDashboard() {
  const { user, isAuthenticated, logout } = useAuth();
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState({ total: 4, healthy: 0, imported: 0, analyses: 0, avgRisk: 0, scoreCount: 0 });
  const [sysHealth, setSysHealth] = useState({ state: 'loading', label: '… Connecting' });
  const [healthModalOpen, setHealthModalOpen] = useState(false);

  const tabs = [
    { id: 'overview',  label: 'Overview',              icon: '◈' },
    { id: 'impact',    label: 'Impact Analysis',       icon: '⚡' },
    { id: 'graph',     label: 'Dependency Graph',      icon: '⬡' },
    { id: 'smells',    label: 'Architectural Smells',  icon: '⚠' },
    { id: 'history',   label: 'Analysis History',      icon: '≡' },
    { id: 'account',   label: 'My Account',            icon: '👤' },
  ];

  useEffect(() => {
    const poll = async () => {
      try {
        const services = await getServices();
        const healthDetails = await getHealth();
        const history = await getHistory(20).catch(() => []);

        const healthy = services.filter(s => s.status === 'healthy').length;
        const imported = services.filter(s => s.status === 'imported').length;
        const total = services.length;
        const scores = services.map(s => s.risk_score).filter(v => typeof v === 'number' && v > 0);
        const avgRisk = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;

        let healthState = 'healthy';
        let label = '● All Systems Go';

        if (healthDetails?.status !== 'healthy') {
          // A response from /health proves the backend is reachable. A
          // dependency outage should be reported as degraded, not offline.
          healthState = 'degraded';
          label = '◐ Infrastructure Degraded';
        } else if (imported > 0 && healthy === 0) {
          healthState = 'imported';
          label = `● ${imported} Services Imported`;
        } else if (total > 0 && healthy === 0) {
          healthState = 'idle';
          label = `○ ${total} Services Offline`;
        } else if (healthy < total) {
          healthState = 'degraded';
          label = `◐ ${healthy}/${total} Services Online`;
        } else {
          healthState = 'healthy';
          label = `● All ${total} Services Online`;
        }

        setSysHealth({ state: healthState, label });
        setStats(s => ({
          ...s,
          total,
          healthy,
          imported,
          avgRisk,
          scoreCount: scores.length,
          analyses: history.length
        }));
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
          {tabs.map(t => (
            <button
              key={t.id}
              className={`nav-tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span className="nav-tab-icon">{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        <div className="nav-status" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Clickable Status Pill that opens deep component health modal */}
          <button
            type="button"
            onClick={() => setHealthModalOpen(true)}
            className={`status-pill ${sysHealth.state}`}
            style={{
              cursor: 'pointer',
              border: 'none',
              background: 'transparent',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontFamily: 'inherit',
              outline: 'none',
              padding: 0
            }}
            title="Click to view live component diagnostics (Neo4j, ChromaDB, AI, GitHub)"
          >
            <span>{sysHealth.label}</span>
            <span style={{ fontSize: '11px', opacity: 0.75 }}>🔍</span>
          </button>

          {isAuthenticated ? (
            <div
              onClick={() => setTab('account')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                background: 'rgba(15, 23, 42, 0.75)',
                padding: '3px 8px 3px 4px',
                borderRadius: '20px',
                border: tab === 'account' ? '1px solid var(--cyan)' : '1px solid rgba(0, 212, 255, 0.3)',
                boxShadow: tab === 'account' ? '0 0 15px rgba(0, 212, 255, 0.35)' : '0 2px 10px rgba(0,0,0,0.3)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              title="Click to view Account & Security details"
            >
              <div style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                background: user?.role === 'admin'
                  ? 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)'
                  : 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontSize: '11px',
                fontWeight: 700
              }}>
                {user?.username?.[0]?.toUpperCase() || 'A'}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
                <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#f8fafc' }}>{user?.username}</span>
                <span style={{ fontSize: '9px', fontWeight: 700, color: user?.role === 'admin' ? 'var(--cyan)' : 'var(--purple)', textTransform: 'uppercase' }}>
                  {user?.role || 'admin'}
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  logout();
                }}
                style={{
                  background: 'rgba(255,255,255,0.06)',
                  border: 'none',
                  borderRadius: '4px',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  fontSize: '11px',
                  padding: '2px 6px',
                  marginLeft: '4px',
                  transition: 'color 0.15s'
                }}
                title="Sign out of current session"
              >
                Logout
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setTab('signin')}
              className="guest-mode-pill"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                background: (tab === 'signin' || tab === 'auth') ? 'rgba(0, 212, 255, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                border: (tab === 'signin' || tab === 'auth') ? '1px solid var(--cyan)' : '1px solid var(--border-md)',
                borderRadius: '20px',
                padding: '4px 12px',
                fontSize: '11.5px',
                color: (tab === 'signin' || tab === 'auth') ? 'var(--cyan)' : 'var(--text-dim)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              title="Operating in Guest Mode. Click to sign in or view security specs."
            >
              <span style={{ fontSize: '11px' }}>🌐</span>
              <span style={{ fontWeight: 500 }}>Guest Mode</span>
            </button>
          )}
        </div>
      </nav>

      {/* ── Main Content ── */}
      <ErrorBoundary>
        <div className="content">
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
                <div className="stat-card" style={{'--accent': (stats.imported > 0 && stats.healthy === 0) ? 'var(--cyan)' : 'var(--green)'}}>
                  <div className="stat-label">{(stats.imported > 0 && stats.healthy === 0) ? 'Imported Services' : 'Healthy'}</div>
                  <div className="stat-value" style={{color: (stats.imported > 0 && stats.healthy === 0) ? 'var(--cyan)' : 'var(--green)'}}>
                    <AnimatedNumber target={(stats.imported > 0 && stats.healthy === 0) ? stats.imported : stats.healthy} />
                  </div>
                  <div className="stat-delta text-dim text-xs">
                    {(stats.imported > 0 && stats.healthy === 0) ? 'architecture modeled' : 'services online'}
                  </div>
                </div>
                <div className="stat-card" style={{'--accent': 'var(--purple)'}}>
                  <div className="stat-label">Analyses Run</div>
                  <div className="stat-value" style={{color:'var(--purple)'}}>
                    <AnimatedNumber target={stats.analyses} />
                  </div>
                  <div className="stat-delta text-dim text-xs">saved analysis history</div>
                </div>
                <div className="stat-card" style={{'--accent': 'var(--orange)'}}>
                  <div className="stat-label">Avg Risk Score</div>
                  <div className="stat-value" style={{color: stats.avgRisk > 50 ? 'var(--orange)' : 'var(--cyan)'}}>
                    {stats.scoreCount ? `${stats.avgRisk}/100` : 'N/A'}
                  </div>
                  <div className="stat-delta text-dim text-xs">
                    {stats.scoreCount ? (stats.avgRisk > 50 ? 'architectural risk detected' : 'low risk baseline') : 'based on last commits'}
                  </div>
                </div>
              </div>

              {/* Services Grid */}
              <div className="section">
                <div className="section-header">
                  <h2 className="section-title">Registered Services</h2>
                  <span className="badge badge-info">{stats.total} configured</span>
                </div>
                <ServiceGrid />
              </div>
            </div>
          )}

          {tab === 'impact' && (
            <div className="anim-fade-up">
              <h1 className="page-title">Impact Analysis</h1>
              <p className="page-sub">Analyze a repository commit or branch with HMDA risk scoring</p>
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
              <p className="page-sub">Saved HMDA analyses — auto-refreshes every 8 seconds</p>
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

          {(tab === 'signin' || tab === 'auth' || tab === 'account') && (
            <AuthPage onNavigateTab={(t) => setTab(t)} />
          )}
        </div>
      </ErrorBoundary>
      <LoginModal onOpenPortal={() => setTab('signin')} />
      <SystemHealthModal isOpen={healthModalOpen} onClose={() => setHealthModalOpen(false)} />
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <MainDashboard />
      </AuthProvider>
    </ToastProvider>
  );
}
