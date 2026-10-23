import { useState, useEffect, useCallback } from 'react';
import { loginUser, registerUser, getCurrentUser, revokeSession } from '../api';
import { clearAnalysisSession } from '../utils/session';
import { AuthContext } from './useAuth';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem('mdt_token'));
  const [user, setUser] = useState(() => {
    try {
      const stored = sessionStorage.getItem('mdt_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [isLoading, setIsLoading] = useState(true);
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  const logout = useCallback(() => {
    const previousToken = sessionStorage.getItem('mdt_token');
    if (previousToken) revokeSession(previousToken).catch(() => {});
    sessionStorage.removeItem('mdt_token');
    sessionStorage.removeItem('mdt_user');
    clearAnalysisSession();
    window.dispatchEvent(new CustomEvent('mdt_session_cleared'));
    setToken(null);
    setUser(null);
  }, []);

  // Check token on initial load
  useEffect(() => {
    // Remove credentials retained by older versions; do not migrate persistent sessions.
    localStorage.removeItem('mdt_token');
    localStorage.removeItem('mdt_user');
    let mounted = true;
    const verifyToken = async () => {
      const storedToken = sessionStorage.getItem('mdt_token');
      if (!storedToken) {
        if (mounted) setIsLoading(false);
        return;
      }

      try {
        const userData = await getCurrentUser();
        if (mounted) {
          setUser(userData);
          sessionStorage.setItem('mdt_user', JSON.stringify(userData));
        }
      } catch {
        if (mounted) {
          logout();
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    verifyToken();

    // Listen to token expiry events
    const handleExpired = () => {
      logout();
      setLoginModalOpen(true);
    };
    window.addEventListener('mdt_auth_expired', handleExpired);

    return () => {
      mounted = false;
      window.removeEventListener('mdt_auth_expired', handleExpired);
    };
  }, [logout]);

  const login = async (username, password) => {
    const data = await loginUser(username, password);
    const accessToken = data.access_token;
    const authUser = data.user;

    clearAnalysisSession();
    window.dispatchEvent(new CustomEvent('mdt_session_cleared'));

    sessionStorage.setItem('mdt_token', accessToken);
    sessionStorage.setItem('mdt_user', JSON.stringify(authUser));

    setToken(accessToken);
    setUser(authUser);
    setLoginModalOpen(false);
    return authUser;
  };

  const register = async (username, password) => {
    const data = await registerUser(username, password);
    const accessToken = data.access_token;
    const authUser = data.user;
    clearAnalysisSession();
    window.dispatchEvent(new CustomEvent('mdt_session_cleared'));

    sessionStorage.setItem('mdt_token', accessToken);
    sessionStorage.setItem('mdt_user', JSON.stringify(authUser));
    setToken(accessToken);
    setUser(authUser);
    setLoginModalOpen(false);
    return authUser;
  };

  const replaceToken = useCallback((accessToken) => {
    sessionStorage.setItem('mdt_token', accessToken);
    setToken(accessToken);
  }, []);

  const value = {
    token,
    user,
    isAuthenticated: !!token && !!user,
    isLoading,
    login,
    register,
    replaceToken,
    logout,
    loginModalOpen,
    openLoginModal: () => setLoginModalOpen(true),
    closeLoginModal: () => setLoginModalOpen(false),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
