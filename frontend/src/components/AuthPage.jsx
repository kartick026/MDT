import { useState } from 'react';
import { useAuth } from '../context/useAuth';
import { refreshToken } from '../api';
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

  return (
    <form onSubmit={submit} className="workspace-form">
      <p className="text-dim">
        Hosted alpha access is by invitation. Your session is kept in this browser tab and is cleared when you sign out.
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
