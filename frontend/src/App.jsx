import { lazy, Suspense, useEffect, useState } from 'react';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/useAuth';
import { readRoute, routeHash } from './utils/analysis';
import './App.css';

const Workspace = lazy(() => import('./components/Workspace'));
const History = lazy(() => import('./components/ProjectHistory'));
const Account = lazy(() => import('./components/AuthPage'));
const Diagnostics = lazy(() => import('./components/Diagnostics'));
const LoginModal = lazy(() => import('./components/LoginModal'));

function MainDashboard() {
  const { user, isAuthenticated, loginModalOpen } = useAuth();
  const [route, setRoute] = useState(() => readRoute(location.hash));
  const [diagnostics, setDiagnostics] = useState(false);
  useEffect(() => {
    const update = () => setRoute(readRoute(location.hash));
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const navigate = tab => { location.hash = routeHash(tab, route); };
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a>
    <header className="app-header">
      <a className="app-brand" href={routeHash('projects')}>MDT <span>Architecture review</span></a>
      <nav className="primary-nav" aria-label="Main navigation">
        {['projects', 'history', 'account'].map(tab => <a key={tab} aria-current={route.tab === tab ? 'page' : undefined} href={routeHash(tab, route)}>{tab[0].toUpperCase() + tab.slice(1)}</a>)}
      </nav>
      <span className="session-label">{isAuthenticated ? user.username : 'Public demo'}</span>
    </header>
    <main id="main-content" className="content" tabIndex={-1}>
      <ErrorBoundary key={route.tab}><Suspense fallback={<p role="status">Loading view…</p>}>
        {route.tab === 'projects' && <Workspace onSignIn={() => navigate('account')} />}
        {route.tab === 'history' && <History onSignIn={() => navigate('account')} />}
        {route.tab === 'account' && <Account onNavigateTab={navigate} />}
      </Suspense></ErrorBoundary>
    </main>
    <footer className="app-footer"><span>Academic alpha · Evidence-based architecture review</span>{import.meta.env.VITE_ENABLE_LOCAL_DASHBOARD === 'true' && isAuthenticated && <button className="btn btn-ghost" onClick={() => setDiagnostics(true)}>Local diagnostics</button>}</footer>
    <ErrorBoundary><Suspense fallback={null}>{diagnostics && <Diagnostics onClose={() => setDiagnostics(false)} />}{loginModalOpen && <LoginModal />}</Suspense></ErrorBoundary>
  </div>;
}

function DashboardSession() {
  const { user, isLoading } = useAuth();
  return isLoading ? <p className="state-loading" role="status">Checking your session…</p> : <MainDashboard key={user?.username || 'guest'} />;
}

export default function App() {
  return <ToastProvider><AuthProvider><DashboardSession /></AuthProvider></ToastProvider>;
}
