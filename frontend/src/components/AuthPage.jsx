import { useState } from 'react';
import { useAuth } from '../context/useAuth';
import { refreshToken } from '../api';
import { startNeonSignIn } from '../utils/neonAuth';
import { routeHash } from '../utils/analysis';
import { Check, Copy, History, Network, RotateCw, Zap } from 'lucide-react';

export function SignInForm({ onSuccess }) {
  const { login, register } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async event => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await (registering ? register : login)(username.trim(), password);
      setPassword('');
      onSuccess?.();
    } catch (err) {
      setError(String(err.response?.data?.detail || 'Sign-in failed. Check your credentials or try again when the server is available.'));
    } finally {
      setBusy(false);
    }
  };

  const handleOAuth = async (provider = 'google') => {
    setBusy(true);
    setError('');
    try {
      await startNeonSignIn(provider);
      // Both SDK redirect and popup flows resume through AuthProvider.
      setBusy(false);
    } catch (err) {
      setError(String(err.response?.data?.detail || err.message || 'Neon OAuth initialization failed.'));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="workspace-form">
      {/* Neon OAuth Provider */}
      <div style={{ marginBottom: '16px' }}>
        <button
          type="button"
          className="btn btn-secondary"
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '10px',
            padding: '10px 16px',
            fontSize: '13px',
            fontWeight: '600',
            background: 'var(--surface-raised, #1e222b)',
            border: '1px solid var(--border-color, #2d3342)',
            borderRadius: '8px',
            color: 'var(--text-main, #e2e8f0)',
            cursor: 'pointer',
            transition: 'all 0.15s ease'
          }}
          onClick={() => handleOAuth('google')}
          disabled={busy}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
          </svg>
          Continue with Google (Neon Auth)
        </button>

        <div style={{ display: 'flex', alignItems: 'center', margin: '14px 0 10px', color: 'var(--text-dim, #64748b)', fontSize: '11px' }}>
          <div style={{ flex: 1, height: '1px', background: 'var(--border-color, #2d3342)' }}></div>
          <span style={{ padding: '0 8px' }}>or sign in with password</span>
          <div style={{ flex: 1, height: '1px', background: 'var(--border-color, #2d3342)' }}></div>
        </div>
      </div>

      <p className="text-dim">
        Sign in to access your saved projects and history. Your session stays in this browser tab until you sign out or it expires.
      </p>

      {/* Quick fill for demo/default admin */}
      {import.meta.env.VITE_ENABLE_LOCAL_DASHBOARD === 'true' && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) && <div className="preset-pills-row" style={{ margin: '4px 0 12px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Default demo credentials:</span>
        <button
          type="button"
          className="preset-pill-btn"
          onClick={() => { setUsername('admin'); setPassword('admin123'); }}
        >
          <Zap size={14} aria-hidden="true" /> Fill Admin (admin / admin123)
        </button>
      </div>}

      <label>
        Username
        <input
          className="form-input"
          value={username}
          onChange={event => setUsername(event.target.value)}
          autoComplete="username"
          required
        />
      </label>
      <label>
        Password
        <input
          className="form-input"
          type="password"
          value={password}
          onChange={event => setPassword(event.target.value)}
          autoComplete={registering ? 'new-password' : 'current-password'}
          required
          minLength={registering ? 8 : undefined}
        />
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="workspace-actions" style={{ marginTop: '8px' }}>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Please wait…' : registering ? 'Create account' : 'Sign in'}
        </button>
        {import.meta.env.VITE_ALLOW_SIGNUP === 'true' && (
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => { setRegistering(!registering); setError(''); }}
          >
            {registering ? 'Use existing account' : 'Create an account'}
          </button>
        )}
      </div>
    </form>
  );
}

export default function AuthPage({ onNavigateTab }) {
  const { user, token, isAuthenticated, logout, replaceToken } = useAuth();
  const [message, setMessage] = useState('');
  const [copiedToken, setCopiedToken] = useState(false);
  const [busy, setBusy] = useState(false);

  const copyToken = async () => {
    try {
      await navigator.clipboard.writeText(token);
      setCopiedToken(true);
      setMessage('Session token copied to clipboard! Use it in the MDT CLI hook or VSCode extension.');
      setTimeout(() => setCopiedToken(false), 2500);
    } catch {
      setMessage('Clipboard access is unavailable. Please copy the token manually.');
    }
  };

  const extend = async () => {
    setBusy(true);
    try {
      const response = await refreshToken();
      replaceToken(response.access_token);
      setMessage('✓ Session successfully renewed.');
      setTimeout(() => setMessage(''), 3000);
    } catch {
      setMessage('Could not renew this session. Please sign in again.');
    } finally {
      setBusy(false);
    }
  };

  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : 'US';

  return (
    <section className="card workspace-account">
      <div className="findings-header">
        <div className="findings-header-text">
          <h1 className="page-title" style={{ margin: 0 }}>
            {isAuthenticated ? 'Your account' : 'Sign in to MDT'}
          </h1>
        </div>
      </div>

      {isAuthenticated ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '12px' }}>
          {/* User Profile Card */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            padding: '16px 20px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '10px',
            border: '1px solid var(--border)'
          }}>
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: '50%',
              background: 'var(--cyan-dim)',
              color: 'var(--cyan)',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '16px',
              flexShrink: 0
            }}>
              {initials}
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <strong style={{ fontSize: '16px', color: 'var(--text)' }}>{user.username}</strong>
                <span className="badge badge-info" style={{ fontSize: '10px', textTransform: 'uppercase' }}>
                  {user.role || 'User'}
                </span>
              </div>
              <span className="text-dim" style={{ fontSize: '12px' }}>
                Active tab session · Role verified by backend API
              </span>
            </div>
          </div>

          <p className="text-dim" style={{ fontSize: '13px', lineHeight: '1.6', margin: 0 }}>
            Local development and CLI tools connect using your tab session token. Signing out terminates this session immediately.
          </p>

          <div className="workspace-actions" style={{ flexWrap: 'wrap', gap: '10px' }}>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={copyToken}
            >
              {copiedToken ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}{copiedToken ? 'Token copied' : 'Copy session token'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy}
              onClick={extend}
            >
              <RotateCw size={15} aria-hidden="true" />{busy ? 'Renewing…' : 'Renew session'}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onNavigateTab?.('projects')}
            >
              Open projects →
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={logout}
              style={{ color: 'var(--red)' }}
            >
              Sign out
            </button>
          </div>

          {message && (
            <p role="status" className="badge badge-info" style={{ display: 'inline-block', margin: 0, padding: '6px 12px' }}>
              {message}
            </p>
          )}

          {/* Quick nav cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginTop: '8px' }}>
            <a
              href={routeHash('projects', { projectId: 'demo' })}
              className="action-pill"
              style={{ justifyContent: 'center', padding: '12px' }}
            >
              <Network size={16} aria-hidden="true" />Explore reference demo
            </a>
            <a
              href={routeHash('history')}
              className="action-pill"
              style={{ justifyContent: 'center', padding: '12px' }}
            >
              <History size={16} aria-hidden="true" />View analysis history
            </a>
          </div>
        </div>
      ) : (
        <SignInForm onSuccess={() => onNavigateTab?.('projects')} />
      )}
    </section>
  );
}
