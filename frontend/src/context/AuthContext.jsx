import { useState, useEffect, useCallback, useRef } from 'react';
import { loginUser, registerUser, getCurrentUser, revokeSession } from '../api';
import { exchangeNeonSession, signOutNeon } from '../utils/neonAuth';
import { clearAnalysisSession } from '../utils/session';
import { AuthContext } from './useAuth';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem('mdt_token'));
  const [user, setUser] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('mdt_user') || 'null'); }
    catch { return null; }
  });
  const [isLoading, setIsLoading] = useState(true);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [sessionError, setSessionError] = useState('');
  const sessionVersion = useRef(0);

  const acceptSession = useCallback((data, provider = 'password') => {
    sessionVersion.current += 1;
    clearAnalysisSession();
    window.dispatchEvent(new CustomEvent('mdt_session_cleared'));
    sessionStorage.setItem('mdt_token', data.access_token);
    sessionStorage.setItem('mdt_user', JSON.stringify(data.user));
    sessionStorage.setItem('mdt_auth_provider', provider);
    setToken(data.access_token);
    setUser(data.user);
    setSessionError('');
    setLoginModalOpen(false);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    sessionVersion.current += 1;
    const previousToken = sessionStorage.getItem('mdt_token');
    const provider = sessionStorage.getItem('mdt_auth_provider');
    if (previousToken) revokeSession(previousToken).catch(() => {});
    if (provider === 'neon') signOutNeon().catch(() => {});
    clearAnalysisSession();
    window.dispatchEvent(new CustomEvent('mdt_session_cleared'));
    setToken(null);
    setUser(null);
    setSessionError('');
  }, []);

  useEffect(() => {
    localStorage.removeItem('mdt_token');
    localStorage.removeItem('mdt_user');
    let mounted = true;
    const version = sessionVersion.current;
    const current = () => mounted && version === sessionVersion.current;
    const verify = async () => {
      const storedToken = sessionStorage.getItem('mdt_token');
      const params = new URLSearchParams(window.location.search);
      const callback = params.has('neon_auth_session_verifier') || sessionStorage.getItem('mdt_oauth_pending');
      try {
        if (storedToken) {
          const profile = await getCurrentUser();
          if (current()) {
            setUser(profile);
            sessionStorage.setItem('mdt_user', JSON.stringify(profile));
          }
        } else if (callback) {
          const data = await exchangeNeonSession();
          if (current()) acceptSession(data, 'neon');
        }
      } catch (error) {
        if (current()) {
          if (storedToken && error.response?.status === 401) logout();
          else setSessionError(storedToken
            ? 'Session verification is temporarily unavailable. Your saved projects and history are retained. Refresh to retry.'
            : String(error.response?.data?.detail || error.message || 'Social sign-in failed. Please try again.'));
        }
      } finally {
        if (mounted) setIsLoading(false);
        if (callback && mounted) {
          sessionStorage.removeItem('mdt_oauth_pending');
          params.delete('neon_auth_session_verifier');
          const search = params.toString();
          window.history.replaceState({}, document.title, window.location.pathname + (search ? `?${search}` : '') + window.location.hash);
        }
      }
    };
    verify();
    const handleExpired = () => { logout(); setLoginModalOpen(true); };
    window.addEventListener('mdt_auth_expired', handleExpired);
    return () => { mounted = false; window.removeEventListener('mdt_auth_expired', handleExpired); };
  }, [logout, acceptSession]);

  const login = async (username, password) => acceptSession(await loginUser(username, password));
  const register = async (username, password) => acceptSession(await registerUser(username, password));
  const loginOAuth = async () => acceptSession(await exchangeNeonSession(), 'neon');
  const replaceToken = useCallback(accessToken => {
    sessionVersion.current += 1;
    sessionStorage.setItem('mdt_token', accessToken);
    setToken(accessToken);
  }, []);

  return <AuthContext.Provider value={{ token, user, isAuthenticated: !!token && !!user, isLoading,
    login, register, loginOAuth, replaceToken, logout, sessionError, loginModalOpen,
    openLoginModal: () => setLoginModalOpen(true), closeLoginModal: () => setLoginModalOpen(false),
  }}>{children}</AuthContext.Provider>;
}
