import axios from 'axios';
import { attachSession, rejectsCurrentSession } from './utils/session';

export const BASE = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({ baseURL: BASE, timeout: 60000, withCredentials: true });

// Alpha bearer session is tab-scoped. Never persist it in localStorage.
// A future same-origin BFF can use HttpOnly sessions; sessionStorage is still XSS-readable.
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('mdt_token');
  if (!config.skipSession) attachSession(config.headers, token);
  return config;
}, (error) => Promise.reject(error));

// Global response interceptor for session expiry handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (rejectsCurrentSession(error, sessionStorage.getItem('mdt_token'))) {
      // If token expired or invalid, clear stored session
      if (sessionStorage.getItem('mdt_token')) {
        sessionStorage.removeItem('mdt_token');
        sessionStorage.removeItem('mdt_user');
        window.dispatchEvent(new CustomEvent('mdt_auth_expired'));
      }
    }
    return Promise.reject(error);
  }
);

// Auth endpoints
export const loginUser = (username, password) =>
  api.post('/auth/login', { username, password }, { skipSession: true }).then(r => r.data);

export const registerUser = (username, password) =>
  api.post('/auth/register', { username, password }, { skipSession: true }).then(r => r.data);

export const getCurrentUser = () =>
  api.get('/auth/me').then(r => r.data);

export const refreshToken = () =>
  api.post('/auth/refresh').then(r => r.data);

export const revokeSession = token =>
  api.post('/auth/logout', {}, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.data);

export const getOAuthConfig = () => api.get('/auth/oauth/config').then(r => r.data);

export const loginWithOAuth = (payload) =>
  api.post('/auth/oauth-login', payload, { skipSession: true }).then(r => r.data);

export const listProjects = (options = {}) => api.get('/v1/projects', options).then(r => r.data.projects || []);
export const getProject = (id, options = {}) => api.get(`/v1/projects/${encodeURIComponent(id)}`, options).then(r => r.data);
export const deleteProject = id => api.delete(`/v1/projects/${encodeURIComponent(id)}`).then(r => r.data);
export const createProject = payload => api.post('/v1/projects', payload, { timeout: 120000 }).then(r => r.data);
export const startAnalysisJob = (projectId, payload) => api.post(`/v1/projects/${encodeURIComponent(projectId)}/analyses`, payload).then(r => r.data);
export const getAnalysisJob = (id, options = {}) => api.get(`/v1/jobs/${encodeURIComponent(id)}`, options).then(r => r.data);
export const cancelAnalysisJob = id => api.delete(`/v1/jobs/${encodeURIComponent(id)}`).then(r => r.data);
export const getAnalysis = (id, options = {}) => api.get(`/v1/analyses/${encodeURIComponent(id)}`, options).then(r => r.data);
export const listAnalyses = (params, options = {}) => api.get('/v1/analyses', { ...options, params }).then(r => r.data);
export const getAnalysisSnapshot = (id, options = {}) => api.get(`/v1/analyses/${encodeURIComponent(id)}/snapshot`, options).then(r => r.data);
export const getFindingReviews = (id, options = {}) => api.get(`/v1/analyses/${encodeURIComponent(id)}/reviews`, options).then(r => r.data);
export const reviewFinding = (id, findingId, payload) => api.put(`/v1/analyses/${encodeURIComponent(id)}/reviews/${encodeURIComponent(findingId)}`, payload).then(r => r.data);
export const getSnapshots = (id, options = {}) => api.get(`/v1/projects/${encodeURIComponent(id)}/snapshots`, options).then(r => r.data);
export const setBaseline = (id, snapshot_version) => api.put(`/v1/projects/${encodeURIComponent(id)}/baseline`, { snapshot_version }).then(r => r.data);
export const getDrift = (id, params, options = {}) => api.get(`/v1/projects/${encodeURIComponent(id)}/drift`, { ...options, params }).then(r => r.data);
export const getPolicies = (id, options = {}) => api.get(`/v1/projects/${encodeURIComponent(id)}/policies`, options).then(r => r.data);
export const savePolicies = (id, rules) => api.put(`/v1/projects/${encodeURIComponent(id)}/policies`, { rules }).then(r => r.data);
export const getDemo = async (options = {}) => {
  try { return (await api.get('/v1/demo', { timeout: 8000, ...options })).data; }
  catch (apiError) {
    if (options.signal?.aborted || axios.isCancel(apiError)) throw apiError;
    const fallback = await fetch(`${import.meta.env.BASE_URL}demo.json`, { signal: options.signal });
    if (!fallback.ok || !fallback.headers.get('content-type')?.includes('json')) throw apiError;
    const data = await fallback.json();
    return { ...data, recorded_fallback: true, label: 'Bundled recorded example; live API unavailable' };
  }
};
export const previewAnalysis = (id, payload, options = {}) => api.post(`/v1/analyses/${encodeURIComponent(id)}/previews`, payload, options).then(r => r.data);

export const getHealth = (options = {}) =>
  api.get('/health/detailed', options).then(r => r.data);

export const getServices = (options = {}) =>
  api.get('/services', options).then(r => {
    const raw = Array.isArray(r.data) ? r.data : (r.data.services || []);
    // Guarantee every field the UI relies on has a safe default
    return raw.map(svc => ({
      name:         svc.name         || 'unknown',
      display_name: svc.display_name || svc.name || 'Unknown Service',
      port:         svc.port         ?? null,
      url:          svc.url          || '',
      description:  svc.description  || '',
      status:       svc.status       || 'unknown',
      risk_level:   (svc.risk_level  || 'UNKNOWN').toUpperCase(),
      risk_score:   svc.risk_score   ?? null,
      api_count:    svc.api_count    || 0,
      dependencies: Array.isArray(svc.dependencies) ? svc.dependencies : [],
    }));
  });

export const getGraph = () =>
  api.get('/services/graph').then(r => r.data);

export const getProjectContext = () =>
  api.get('/registry/context').then(r => r.data);

export const getSmells = () =>
  api.get('/services/smells').then(r => r.data);

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
