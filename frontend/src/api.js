import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: BASE, timeout: 60000 });

// Attach JWT access token if present in localStorage
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('mdt_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => Promise.reject(error));

// Global response interceptor for session expiry handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // If token expired or invalid, clear stored session
      if (localStorage.getItem('mdt_token')) {
        localStorage.removeItem('mdt_token');
        localStorage.removeItem('mdt_user');
        window.dispatchEvent(new CustomEvent('mdt_auth_expired'));
      }
    }
    return Promise.reject(error);
  }
);

// Auth endpoints
export const loginUser = (username, password) =>
  api.post('/auth/login', { username, password }).then(r => r.data);

export const registerUser = (username, password) =>
  api.post('/auth/register', { username, password }).then(r => r.data);

export const getCurrentUser = () =>
  api.get('/auth/me').then(r => r.data);

export const refreshToken = () =>
  api.post('/auth/refresh').then(r => r.data);

export const getHealth = () =>
  api.get('/health/detailed').then(r => r.data);

export const getServices = () =>
  api.get('/services').then(r => {
    const raw = Array.isArray(r.data) ? r.data : (r.data.services || []);
    // Guarantee every field the UI relies on has a safe default
    return raw.map(svc => ({
      name:         svc.name         || 'unknown',
      display_name: svc.display_name || svc.name || 'Unknown Service',
      port:         svc.port         || 0,
      url:          svc.url          || '',
      description:  svc.description  || '',
      status:       svc.status       || 'unknown',
      risk_level:   (svc.risk_level  || 'UNKNOWN').toUpperCase(),
      risk_score:   svc.risk_score   || 0,
      api_count:    svc.api_count    || 0,
      dependencies: Array.isArray(svc.dependencies) ? svc.dependencies : [],
    }));
  });

export const getGraph = () =>
  api.get('/services/graph').then(r => r.data);

export const getProjectContext = () =>
  api.get('/registry/context').then(r => r.data);

export const getSmells = () =>
  api.get('/services/smells').then(r => r.data.smells || []);

export const getHistory = (limit = 20) =>
  api.get(`/analysis/history?limit=${limit}`).then(r => r.data.analyses || []);

export const analyzeImpact = payload =>
  api.post('/analysis/analyze', payload, { timeout: 120000 }).then(r => r.data);

export const importRepo = payload =>
  api.post('/registry/import-repo', payload, { timeout: 120000 }).then(r => r.data);

export const getConnectionBugs = () =>
  api.get('/registry/connection-bugs').then(r => r.data.bugs || []);

export const previewFix = (payload) =>
  api.post('/analysis/preview-fix', payload, { timeout: 120000 }).then(r => r.data);

export const resetDefaultRegistry = () =>
  api.post('/registry/reset-default').then(r => r.data);

export default api;
