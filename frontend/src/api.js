import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: BASE, timeout: 60000 });

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

export default api;
