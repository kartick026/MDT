import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from './Toast';
import { getHealth } from '../api';

export default function LoginModal({ onOpenPortal }) {
  const { loginModalOpen, closeLoginModal, login } = useAuth();
  const { addToast } = useToast();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gatewayOnline, setGatewayOnline] = useState(true);

  // Ping backend on open
  useEffect(() => {
    if (loginModalOpen) {
      setError(null);
      getHealth()
        .then(() => setGatewayOnline(true))
        .catch(() => setGatewayOnline(false));
    }
  }, [loginModalOpen]);

  if (!loginModalOpen) return null;

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const user = await login(username.trim(), password);
      addToast(`Logged in successfully as ${user.username}`, 'success');
      closeLoginModal();
    } catch (err) {
      console.error('Login modal error:', err);
      let msg = 'Authentication failed. Please check your credentials.';
      if (!err.response || err.code === 'ERR_NETWORK') {
        msg = 'Cannot reach MDT Backend at http://localhost:8000. Please ensure the backend server is running.';
        setGatewayOnline(false);
      } else if (err.response.status === 401) {
        msg = 'Invalid username or password. Click the Admin Demo button below.';
      } else if (err.response.status === 404) {
        msg = 'Authentication route not found (404). Please ensure backend is running with /auth routes.';
      } else if (err.response?.data?.detail) {
        msg = String(err.response.data.detail);
      }
      setError(msg);
      addToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickFill = (u, p) => {
    setUsername(u);
    setPassword(p);
    setError(null);
  };

  return (
    <div className="login-modal-backdrop" onClick={closeLoginModal}>
      <div className="login-modal-dialog anim-scale-up" onClick={(e) => e.stopPropagation()}>
        {/* Glow ambient layer */}
        <div className="modal-ambient-glow"></div>

        {/* Close Button */}
        <button
          type="button"
          onClick={closeLoginModal}
          className="modal-close-icon-btn"
          title="Close dialog"
        >
          ✕
        </button>

        {/* Header */}
        <div className="modal-header-block">
          <div className="modal-badge-row">
            <span className="modal-shield-emblem">🛡️</span>
            <span className={`modal-status-badge ${gatewayOnline ? 'online' : 'offline'}`}>
              <span className="badge-dot"></span>
              {gatewayOnline ? 'API Online (:8000)' : 'API Offline'}
            </span>
          </div>
          <h2 className="modal-title">MDT Security Sign In</h2>
          <p className="modal-desc">
            Authenticate to perform protected cross-service operations, repository imports, and architectural fixes.
          </p>
        </div>

        {/* Error notification */}
        {error && (
          <div className="modal-alert-box error">
            <span className="alert-icon">⚠️</span>
            <span className="alert-text">{error}</span>
          </div>
        )}

        {!gatewayOnline && (
          <div className="modal-alert-box warning">
            <span className="alert-icon">🔌</span>
            <span className="alert-text">
              MDT Backend server is currently unreachable. Make sure the backend process on port 8000 is active.
            </span>
          </div>
        )}

        {/* Quick Demo Fill Pills */}
        <div className="modal-demo-pills">
          <span className="demo-pills-title">Quick Demo:</span>
          <button
            type="button"
            className="demo-pill-btn"
            onClick={() => handleQuickFill('admin', 'admin123')}
          >
            <span className="pill-tag admin">ADMIN</span>
            <span>admin</span>
          </button>
          <button
            type="button"
            className="demo-pill-btn"
            onClick={() => handleQuickFill('auditor', 'auditor123')}
          >
            <span className="pill-tag viewer">VIEWER</span>
            <span>auditor</span>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="modal-form">
          <div className="modal-field">
            <label htmlFor="modal-username" className="modal-field-label">
              Username
            </label>
            <div className="modal-input-wrap">
              <span className="field-icon">👤</span>
              <input
                id="modal-username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. admin"
                className="modal-input"
                autoComplete="username"
              />
            </div>
          </div>

          <div className="modal-field">
            <div className="modal-field-header">
              <label htmlFor="modal-password" className="modal-field-label">
                Password
              </label>
              <button
                type="button"
                className="modal-pass-toggle"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? 'Hide 👁️' : 'Show 👁️‍🗨️'}
              </button>
            </div>
            <div className="modal-input-wrap">
              <span className="field-icon">🔒</span>
              <input
                id="modal-password"
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="modal-input"
                autoComplete="current-password"
              />
            </div>
          </div>

          {/* Action Button */}
          <div className="modal-actions-col">
            <button
              type="submit"
              disabled={loading || !username || !password}
              className="modal-submit-btn"
            >
              {loading ? (
                <>
                  <span className="btn-spinner"></span>
                  <span>Authenticating…</span>
                </>
              ) : (
                <>
                  <span>Sign In with JWT</span>
                  <span className="btn-arrow">→</span>
                </>
              )}
            </button>

            {onOpenPortal && (
              <button
                type="button"
                className="modal-switch-portal-btn"
                onClick={() => {
                  closeLoginModal();
                  onOpenPortal();
                }}
              >
                <span>↗ Sign in or create an account</span>
              </button>
            )}
          </div>
        </form>

        <div className="modal-footer-caption">
          <span>HS256 Bearer Token • 24h Session Duration</span>
        </div>
      </div>
    </div>
  );
}
