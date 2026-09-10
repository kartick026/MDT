import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { loginUser, registerUser, getCurrentUser } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('mdt_token'));
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('mdt_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [isLoading, setIsLoading] = useState(true);
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  const logout = useCallback(() => {
    localStorage.removeItem('mdt_token');
    localStorage.removeItem('mdt_user');
    setToken(null);
    setUser(null);
  }, []);

  // Check token on initial load
  useEffect(() => {
    let mounted = true;
    const verifyToken = async () => {
      const storedToken = localStorage.getItem('mdt_token');
      if (!storedToken) {
        if (mounted) setIsLoading(false);
        return;
      }

      try {
        const userData = await getCurrentUser();
        if (mounted) {
          setUser(userData);
          localStorage.setItem('mdt_user', JSON.stringify(userData));
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

    localStorage.setItem('mdt_token', accessToken);
    localStorage.setItem('mdt_user', JSON.stringify(authUser));

    setToken(accessToken);
    setUser(authUser);
    setLoginModalOpen(false);
    return authUser;
  };

  const register = async (username, password) => {
    const data = await registerUser(username, password);
    const accessToken = data.access_token;
    const authUser = data.user;

    localStorage.setItem('mdt_token', accessToken);
    localStorage.setItem('mdt_user', JSON.stringify(authUser));
    setToken(accessToken);
    setUser(authUser);
    setLoginModalOpen(false);
    return authUser;
  };

  const replaceToken = useCallback((accessToken) => {
    localStorage.setItem('mdt_token', accessToken);
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

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
