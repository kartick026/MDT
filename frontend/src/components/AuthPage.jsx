import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from './Toast';
import { getHealth, refreshToken as apiRefreshToken } from '../api';

export default function AuthPage({ onNavigateTab }) {
  const { user, token, isAuthenticated, login, register, replaceToken, logout } = useAuth();
  const { addToast } = useToast();

  const [authTab, setAuthTab] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [signupUsername, setSignupUsername] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [signupConfirm, setSignupConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gatewayStatus, setGatewayStatus] = useState({ online: null, latency: null, checking: true });
  const [copiedToken, setCopiedToken] = useState(false);
  const [refreshingToken, setRefreshingToken] = useState(false);

  // Ping backend gateway for live latency & health
  const checkGateway = async () => {
    setGatewayStatus(s => ({ ...s, checking: true }));
    const start = performance.now();
    try {
      const data = await getHealth();
      const latency = Math.round(performance.now() - start);
      setGatewayStatus({
        online: data.status === 'healthy',
        latency,
        checking: false,
        version: data.version || '1.0.0'
      });
    } catch {
      setGatewayStatus({ online: false, latency: null, checking: false });
    }
  };

  useEffect(() => {
    checkGateway();
    const interval = setInterval(checkGateway, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleLoginSubmit = async (e) => {
    if (e) e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const authUser = await login(username.trim(), password);
      addToast(`Welcome back, ${authUser.username}! Role: ${authUser.role.toUpperCase()}`, 'success');
      setError(null);
    } catch (err) {
      console.error('Login error:', err);
      let msg = 'Authentication failed. Please verify your credentials.';
      if (!err.response || err.code === 'ERR_NETWORK') {
        msg = 'Cannot reach MDT Backend at http://localhost:8000. Please ensure the backend server is running.';
      } else if (err.response.status === 401) {
        msg = 'Invalid username or password. Click one of the Quick Demo chips below.';
      } else if (err.response.status === 404) {
        msg = 'Authentication route not found (404). Please ensure the backend server on port 8000 has the latest auth endpoints.';
      } else if (err.response?.data?.detail) {
        msg = String(err.response.data.detail);
      }
      setError(msg);
      addToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDirectDemoLogin = async (u, p) => {
    setUsername(u);
    setPassword(p);
    setError(null);
    setLoading(true);
    try {
      const authUser = await login(u, p);
      addToast(`Signed in instantly as ${authUser.username} (${authUser.role.toUpperCase()})`, 'success');
      setError(null);
    } catch (err) {
      console.error('Demo login error:', err);
      let msg = 'Cannot connect to backend server. Please verify port 8000 is running.';
      if (!err.response || err.code === 'ERR_NETWORK') {
        msg = 'Cannot reach MDT Backend at http://localhost:8000. Please ensure the backend server is running.';
      } else if (err.response.status === 404) {
        msg = 'Authentication route not found (404). Please ensure the backend server on port 8000 has the latest auth endpoints.';
      } else if (err.response?.data?.detail) {
        msg = String(err.response.data.detail);
      }
      setError(msg);
      addToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (signupPassword !== signupConfirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      const authUser = await register(signupUsername.trim(), signupPassword);
      addToast(`Account created. Welcome, ${authUser.username}!`, 'success');
    } catch (err) {
      const message = err.response?.data?.detail || 'Unable to create account. Please try another username.';
      setError(String(message));
      addToast(String(message), 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyToken = () => {
    if (!token) return;
    navigator.clipboard.writeText(token);
    setCopiedToken(true);
    addToast('JWT Bearer Token copied to clipboard', 'info');
    setTimeout(() => setCopiedToken(false), 2500);
  };

  const handleRefreshToken = async () => {
    setRefreshingToken(true);
    try {
      const res = await apiRefreshToken();
      replaceToken(res.access_token);
      addToast('Session token refreshed successfully (extended 24 hours)', 'success');
    } catch (err) {
      addToast('Failed to refresh token: ' + (err.response?.data?.detail || err.message), 'error');
    } finally {
      setRefreshingToken(false);
    }
  };

  return (
    <div className="auth-portal-wrapper anim-fade-up">
      {/* ── Header ── */}
      <div className="auth-header-section">
        <div className="auth-shield-badge">
          <span className="auth-shield-icon">🛡️</span>
          <div className="auth-shield-glow"></div>
        </div>
        <div className="auth-header-text">
          <div className="auth-kicker">MDT Security & Operator Gateway</div>
          <h1 className="auth-title">
            {isAuthenticated ? 'Operator Identity & Session Dashboard' : 'Sign In to MDT'}
          </h1>
          <p className="auth-subtitle">
            {isAuthenticated
              ? `Currently authenticated as ${user?.username} with ${user?.role === 'admin' ? 'full administrative mutation privileges' : 'read-only inspection access'}.`
              : 'Explore the platform as a guest, sign in to administer it, or create a read-only viewer account for saved access.'}
          </p>
        </div>

        {/* Live gateway health indicator */}
        <div className="auth-gateway-pill" onClick={checkGateway} title="Click to test live gateway latency">
          <span className={`gateway-dot ${gatewayStatus.online ? 'online' : gatewayStatus.online === false ? 'offline' : 'checking'}`}></span>
          <span className="gateway-label">
            {gatewayStatus.checking
              ? 'Pinging Gateway…'
              : gatewayStatus.online
              ? `Gateway Live (${gatewayStatus.latency}ms)`
              : 'Gateway Offline (:8000)'}
          </span>
          <span className="gateway-refresh-icon">↻</span>
        </div>
      </div>

      {/* ── Main Auth Card ── */}
      {!isAuthenticated ? (
        <div className="auth-card-container">
          {/* Public Mode Notice */}
          <div className="auth-public-notice">
            <span className="public-notice-icon">💡</span>
            <div className="public-notice-body">
              <strong>MDT is fully operational in Guest Mode:</strong>
              <span> You can explore all services, inspect dependency topologies, and run live impact analyses right now without signing in. Signing in is only required for administrative mutation controls (importing external repos, fixing architectural smells, or resetting registries).</span>
            </div>
          </div>

          {/* Tabs Navigation */}
          <div className="auth-tabs-nav">
            <button
              type="button"
              className={`auth-nav-btn ${authTab === 'login' ? 'active' : ''}`}
              onClick={() => setAuthTab('login')}
            >
              <span>🔑</span>
              <span>Credentials Login</span>
            </button>
            <button
              type="button"
              className={`auth-nav-btn ${authTab === 'signup' ? 'active' : ''}`}
              onClick={() => { setAuthTab('signup'); setError(null); }}
            >
              <span>✨</span>
              <span>Create Account</span>
            </button>
            <button
              type="button"
              className={`auth-nav-btn ${authTab === 'demo' ? 'active' : ''}`}
              onClick={() => setAuthTab('demo')}
            >
              <span>⚡</span>
              <span>1-Click Demo Profiles</span>
            </button>
            <button
              type="button"
              className={`auth-nav-btn ${authTab === 'spec' ? 'active' : ''}`}
              onClick={() => setAuthTab('spec')}
            >
              <span>📜</span>
              <span>Security & Token Spec</span>
            </button>
          </div>

          {/* TAB 1: Credentials Login */}
          {authTab === 'login' && (
            <div className="auth-tab-content anim-fade-in">
              {error && (
                <div className="auth-alert error">
                  <span className="auth-alert-icon">⚠️</span>
                  <div className="auth-alert-body">
                    <strong>Authentication Error:</strong> {error}
                  </div>
                </div>
              )}

              {gatewayStatus.online === false && (
                <div className="auth-alert warning">
                  <span className="auth-alert-icon">🔌</span>
                  <div className="auth-alert-body">
                    <strong>Backend Server Unreachable:</strong> The MDT API on port 8000 is not responding. Please make sure the Python server or Docker container is started.
                  </div>
                  <button type="button" className="auth-retry-btn" onClick={checkGateway}>
                    Retry Ping
                  </button>
                </div>
              )}

              {/* Quick Fill Demo Chips */}
              <div className="auth-chips-bar">
                <span className="auth-chips-label">Autofill credentials:</span>
                <button
                  type="button"
                  className="auth-chip-btn"
                  onClick={() => { setUsername('admin'); setPassword('admin123'); setError(null); }}
                >
                  <span className="chip-badge admin">ADMIN</span>
                  <span>admin / admin123</span>
                </button>
                <button
                  type="button"
                  className="auth-chip-btn"
                  onClick={() => { setUsername('auditor'); setPassword('auditor123'); setError(null); }}
                >
                  <span className="chip-badge viewer">VIEWER</span>
                  <span>auditor / auditor123</span>
                </button>
              </div>

              <form onSubmit={handleLoginSubmit} className="auth-form">
                <div className="auth-field-group">
                  <label htmlFor="portal-username" className="auth-label">
                    Username or Operator ID
                  </label>
                  <div className="auth-input-wrapper">
                    <span className="input-prefix-icon">👤</span>
                    <input
                      id="portal-username"
                      type="text"
                      required
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="e.g. admin"
                      className="auth-text-input"
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div className="auth-field-group">
                  <div className="auth-label-row">
                    <label htmlFor="portal-password" className="auth-label">
                      Secret Password
                    </label>
                    <button
                      type="button"
                      className="auth-show-pass-toggle"
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? 'Hide 👁️' : 'Show 👁️‍🗨️'}
                    </button>
                  </div>
                  <div className="auth-input-wrapper">
                    <span className="input-prefix-icon">🔒</span>
                    <input
                      id="portal-password"
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="auth-text-input"
                      autoComplete="current-password"
                    />
                  </div>
                </div>

                <div className="auth-submit-row">
                  <button
                    type="submit"
                    disabled={loading || !username || !password}
                    className="auth-submit-btn"
                  >
                    {loading ? (
                      <>
                        <span className="spinner-dot"></span>
                        <span>Verifying Credentials…</span>
                      </>
                    ) : (
                      <>
                        <span>🛡️ Sign In with JWT Bearer</span>
                        <span className="auth-btn-arrow">→</span>
                      </>
                    )}
                  </button>
                </div>
              </form>

              <div className="auth-footer-notice">
                <span>🔒 Secured via HS256 signed JSON Web Tokens. Passwords verified with bcrypt salting.</span>
              </div>
            </div>
          )}

          {authTab === 'signup' && (
            <div className="auth-tab-content anim-fade-in">
              {error && (
                <div className="auth-alert error" role="alert">
                  <span className="auth-alert-icon">⚠️</span>
                  <div className="auth-alert-body">{error}</div>
                </div>
              )}
              <div className="signup-intro">
                <span className="signup-icon">✨</span>
                <div>
                  <h3>Create a viewer account</h3>
                  <p>Viewer accounts can inspect services, dependency graphs, drift results, and architectural smells. Administrative changes always require an administrator.</p>
                </div>
              </div>
              <form onSubmit={handleSignupSubmit} className="auth-form" noValidate>
                <div className="auth-field-group">
                  <label htmlFor="signup-username" className="auth-label">Username</label>
                  <div className="auth-input-wrapper">
                    <span className="input-prefix-icon">👤</span>
                    <input id="signup-username" type="text" required minLength="3" maxLength="100" value={signupUsername} onChange={(e) => setSignupUsername(e.target.value)} placeholder="e.g. alex.chen" className="auth-text-input" autoComplete="username" />
                  </div>
                  <span className="auth-field-hint">3–100 characters: letters, numbers, periods, underscores, or hyphens.</span>
                </div>
                <div className="auth-field-group">
                  <label htmlFor="signup-password" className="auth-label">Password</label>
                  <div className="auth-input-wrapper">
                    <span className="input-prefix-icon">🔒</span>
                    <input id="signup-password" type="password" required minLength="8" maxLength="128" value={signupPassword} onChange={(e) => setSignupPassword(e.target.value)} placeholder="At least 8 characters" className="auth-text-input" autoComplete="new-password" />
                  </div>
                </div>
                <div className="auth-field-group">
                  <label htmlFor="signup-confirm" className="auth-label">Confirm password</label>
                  <div className="auth-input-wrapper">
                    <span className="input-prefix-icon">🔒</span>
                    <input id="signup-confirm" type="password" required minLength="8" value={signupConfirm} onChange={(e) => setSignupConfirm(e.target.value)} placeholder="Repeat your password" className="auth-text-input" autoComplete="new-password" />
                  </div>
                </div>
                <div className="auth-submit-row">
                  <button type="submit" disabled={loading || !signupUsername || !signupPassword || !signupConfirm} className="auth-submit-btn">
                    {loading ? <><span className="spinner-dot" /><span>Creating account…</span></> : <><span>Create viewer account</span><span className="auth-btn-arrow">→</span></>}
                  </button>
                </div>
              </form>
              <p className="auth-footer-notice">Already have an account? <button type="button" className="auth-inline-link" onClick={() => { setAuthTab('login'); setError(null); }}>Sign in instead</button></p>
            </div>
          )}

          {/* TAB 2: 1-Click Demo Profiles */}
          {authTab === 'demo' && (
            <div className="auth-tab-content anim-fade-in">
              <p className="demo-intro-text">
                Select a pre-configured security persona below for instantaneous 1-click evaluation without typing passwords.
              </p>

              <div className="demo-profiles-grid">
                {/* Admin Card */}
                <div className="demo-profile-card admin-border">
                  <div className="profile-card-top">
                    <div className="profile-avatar admin">A</div>
                    <div>
                      <div className="profile-name">System Administrator</div>
                      <div className="profile-role-pill admin">ADMIN ROLE</div>
                    </div>
                  </div>
                  <p className="profile-desc">
                    Full read & write mutation permissions across the entire platform. Can import repositories, trigger live HMDA analyses, and execute architectural smell fixes.
                  </p>
                  <ul className="profile-caps-list">
                    <li><span className="cap-check">✓</span> Trigger Cross-Service HMDA Impact Engine</li>
                    <li><span className="cap-check">✓</span> Register & Import External Git Repositories</li>
                    <li><span className="cap-check">✓</span> Perform Automated Architectural Smell Fixes</li>
                    <li><span className="cap-check">✓</span> Reset Default Microservice Registry</li>
                  </ul>
                  <button
                    type="button"
                    disabled={loading}
                    className="demo-card-btn admin-btn"
                    onClick={() => handleDirectDemoLogin('admin', 'admin123')}
                  >
                    ⚡ Instant Sign In as Admin
                  </button>
                </div>

                {/* Auditor Card */}
                <div className="demo-profile-card viewer-border">
                  <div className="profile-card-top">
                    <div className="profile-avatar viewer">V</div>
                    <div>
                      <div className="profile-name">Security & Drift Auditor</div>
                      <div className="profile-role-pill viewer">VIEWER ROLE</div>
                    </div>
                  </div>
                  <p className="profile-desc">
                    Read-only operational access designed for compliance audits, drift observation, and dependency graph tracing without risk of mutating cluster configuration.
                  </p>
                  <ul className="profile-caps-list">
                    <li><span className="cap-check">✓</span> Inspect Dependency Graph & Risk Topology</li>
                    <li><span className="cap-check">✓</span> Read Architectural Smells & Remediation Guides</li>
                    <li><span className="cap-check">✓</span> View Historical Analysis Logs</li>
                    <li><span className="cap-lock">🔒</span> Modifying service configurations (Restricted)</li>
                  </ul>
                  <button
                    type="button"
                    disabled={loading}
                    className="demo-card-btn viewer-btn"
                    onClick={() => handleDirectDemoLogin('auditor', 'auditor123')}
                  >
                    ⚡ Instant Sign In as Auditor
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Security & Token Spec */}
          {authTab === 'spec' && (
            <div className="auth-tab-content anim-fade-in">
              <div className="spec-block">
                <h3 className="spec-heading">MDT Authentication Protocol</h3>
                <p className="spec-paragraph">
                  The Microservice Drift Tracker uses stateless JSON Web Tokens (JWT) adhering to RFC 7519 standards.
                  Each token is cryptographically signed using HS256 and verified on every mutation route via FastAPI dependency injection.
                </p>

                <div className="spec-grid">
                  <div className="spec-item">
                    <span className="spec-item-label">Token Format</span>
                    <span className="spec-item-val font-mono">Bearer &lt;JWT&gt;</span>
                  </div>
                  <div className="spec-item">
                    <span className="spec-item-label">Signing Algorithm</span>
                    <span className="spec-item-val font-mono">HS256 (HMAC-SHA256)</span>
                  </div>
                  <div className="spec-item">
                    <span className="spec-item-label">Default Expiration</span>
                    <span className="spec-item-val font-mono">24 Hours (1440 minutes)</span>
                  </div>
                  <div className="spec-item">
                    <span className="spec-item-label">Header Injection</span>
                    <span className="spec-item-val font-mono">Authorization: Bearer ...</span>
                  </div>
                </div>

                <h4 className="spec-subheading">Protected Endpoints</h4>
                <div className="spec-endpoints-list">
                  <div className="spec-endpoint">
                    <span className="endpoint-method post">POST</span>
                    <span className="endpoint-path">/registry/import-repo</span>
                    <span className="endpoint-scope">Requires Admin</span>
                  </div>
                  <div className="spec-endpoint">
                    <span className="endpoint-method post">POST</span>
                    <span className="endpoint-path">/analysis/preview-fix</span>
                    <span className="endpoint-scope">Requires Admin</span>
                  </div>
                  <div className="spec-endpoint">
                    <span className="endpoint-method post">POST</span>
                    <span className="endpoint-path">/registry/reset-default</span>
                    <span className="endpoint-scope">Requires Admin</span>
                  </div>
                  <div className="spec-endpoint">
                    <span className="endpoint-method get">GET</span>
                    <span className="endpoint-path">/auth/me</span>
                    <span className="endpoint-scope">Any Valid Token</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* ── Authenticated Account Dashboard ── */
        <div className="auth-account-container anim-fade-up">
          {/* Identity Card */}
          <div className="account-hero-card">
            <div className="account-hero-left">
              <div className={`account-avatar ${user?.role === 'admin' ? 'admin' : 'viewer'}`}>
                {user?.username?.[0]?.toUpperCase() || 'U'}
              </div>
              <div className="account-hero-meta">
                <div className="account-badge-row">
                  <span className={`account-role-badge ${user?.role === 'admin' ? 'admin' : 'viewer'}`}>
                    {user?.role?.toUpperCase()}
                  </span>
                  <span className="account-active-badge">● Active Session</span>
                </div>
                <h2 className="account-username">{user?.username}</h2>
                <div className="account-submeta">
                  <span>Signed in via Bearer JWT</span> • <span>Session valid for 24h</span>
                </div>
              </div>
            </div>

            <div className="account-hero-actions">
              <button
                type="button"
                className="account-refresh-btn"
                onClick={handleRefreshToken}
                disabled={refreshingToken}
                title="Extend session by refreshing JWT token"
              >
                <span>{refreshingToken ? 'Refreshing…' : '↻ Extend Session'}</span>
              </button>
              <button
                type="button"
                className="account-logout-btn"
                onClick={() => {
                  logout();
                  addToast('Signed out of session successfully', 'info');
                }}
              >
                <span>⎋ Sign Out</span>
              </button>
            </div>
          </div>

          {/* Token Details & Permissions */}
          <div className="account-details-grid">
            {/* Token Inspector */}
            <div className="account-card">
              <div className="card-header-row">
                <h3 className="card-heading">Active JWT Bearer Token</h3>
                <button
                  type="button"
                  className={`copy-token-btn ${copiedToken ? 'copied' : ''}`}
                  onClick={handleCopyToken}
                >
                  {copiedToken ? '✓ Copied' : '📋 Copy Token'}
                </button>
              </div>
              <p className="card-subtext">
                Injected automatically into all outgoing API requests in the <code className="inline-code">Authorization: Bearer</code> header.
              </p>
              <div className="token-display-box" onClick={handleCopyToken} title="Click to copy full token">
                <code>{token ? `${token.slice(0, 45)}••••••••••••••••${token.slice(-25)}` : 'No active token'}</code>
              </div>
            </div>

            {/* Role Capabilities */}
            <div className="account-card">
              <h3 className="card-heading">Role Permissions Matrix</h3>
              <p className="card-subtext">
                Authorized capabilities based on your assigned role: <strong style={{ color: 'var(--cyan)' }}>{user?.role?.toUpperCase()}</strong>
              </p>
              <div className="perms-grid">
                <div className="perm-item granted">
                  <span className="perm-icon">✓</span>
                  <span className="perm-name">Run HMDA Risk Analysis</span>
                </div>
                <div className="perm-item granted">
                  <span className="perm-icon">✓</span>
                  <span className="perm-name">Inspect Dependency Topology</span>
                </div>
                <div className="perm-item granted">
                  <span className="perm-icon">✓</span>
                  <span className="perm-name">View Architectural Smells</span>
                </div>
                <div className={`perm-item ${user?.role === 'admin' ? 'granted' : 'denied'}`}>
                  <span className="perm-icon">{user?.role === 'admin' ? '✓' : '✕'}</span>
                  <span className="perm-name">Import External Repositories</span>
                </div>
                <div className={`perm-item ${user?.role === 'admin' ? 'granted' : 'denied'}`}>
                  <span className="perm-icon">{user?.role === 'admin' ? '✓' : '✕'}</span>
                  <span className="perm-name">Apply Architectural Smell Fixes</span>
                </div>
                <div className={`perm-item ${user?.role === 'admin' ? 'granted' : 'denied'}`}>
                  <span className="perm-icon">{user?.role === 'admin' ? '✓' : '✕'}</span>
                  <span className="perm-name">Reset Service Registry</span>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Jump Buttons */}
          <div className="account-quick-jumps">
            <span className="jump-label">Quick Jump:</span>
            {onNavigateTab && (
              <>
                <button type="button" className="jump-btn" onClick={() => onNavigateTab('overview')}>
                  ◈ Go to Service Overview
                </button>
                <button type="button" className="jump-btn" onClick={() => onNavigateTab('impact')}>
                  ⚡ Run Impact Analysis
                </button>
                <button type="button" className="jump-btn" onClick={() => onNavigateTab('smells')}>
                  ⚠ View Architectural Smells
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
