/* Small platform-neutral client. No scoring or secrets are embedded in a client. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MDTClient = factory();
})(globalThis, function () {
  'use strict';
  const TERMINAL = new Set(['succeeded', 'completed', 'partial', 'failed', 'cancelled']);

  function validateServerUrl(value) {
    const url = new URL(value);
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) throw new Error('Use HTTPS, or HTTP on localhost for local development.');
    if (url.username || url.password || url.search || url.hash) throw new Error('Server URL cannot contain credentials, a query, or a fragment.');
    return url.href.replace(/\/$/, '');
  }

  function parseGitHubUrl(value) {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com' || url.username || url.password) throw new Error('Open an HTTPS github.com repository, commit, comparison, or pull request.');
    const parts = url.pathname.split('/').filter(Boolean).map(part => decodeURIComponent(part));
    const [owner, name, type, ...tail] = parts;
    if (!owner || !name || !/^[\w.-]+$/.test(owner) || !/^[\w.-]+$/.test(name)) throw new Error('The GitHub repository URL is invalid.');
    const repo = name.replace(/\.git$/, '');
    const result = { repo_url: `https://github.com/${owner}/${repo}`, owner, repo, source: 'commit' };
    if (!type || type === 'tree') return { ...result, ...(tail.length ? { head_ref: tail.join('/') } : {}) };
    if (type === 'commit' && /^[a-fA-F0-9]{7,40}$/.test(tail[0] || '')) return { ...result, head_ref: tail[0] };
    if (type === 'pull' && /^\d+$/.test(tail[0] || '') && Number.isSafeInteger(Number(tail[0])) && Number(tail[0]) > 0) return { ...result, pull_request: Number(tail[0]), comparison_mode: 'merge_base' };
    if (type === 'compare') {
      const comparison = tail.join('/').split('...');
      if (comparison.length === 2 && comparison.every(Boolean)) return { ...result, base_ref: comparison[0], head_ref: comparison[1], comparison_mode: 'merge_base' };
    }
    throw new Error('This GitHub page is unsupported. Use the repository, commit, compare, or pull request page.');
  }

  function analysisPayload(context, project) {
    if (context.repo_url.toLowerCase() !== project.repo_url.replace(/\.git$/, '').replace(/\/$/, '').toLowerCase()) throw new Error('This page does not match the selected MDT project.');
    return {
      source: 'commit',
      ...(context.pull_request ? { pull_request: context.pull_request } : { head_ref: context.head_ref || project.branch || 'main' }),
      ...(context.base_ref ? { base_ref: context.base_ref } : {}),
      ...(context.comparison_mode ? { comparison_mode: context.comparison_mode } : {}),
      ...(project.snapshot_version ? { snapshot_version: project.snapshot_version } : {}),
    };
  }

  function createClient({ baseUrl, token, fetchImpl = globalThis.fetch, timeoutMs = 20000 }) {
    const base = validateServerUrl(baseUrl);
    async function request(path, { method = 'GET', body, signal, idempotencyKey } = {}) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const abort = () => controller.abort();
      signal?.addEventListener('abort', abort, { once: true });
      if (signal?.aborted) controller.abort();
      try {
        const headers = { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
        if (body !== undefined) headers['Content-Type'] = 'application/json';
        if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
        const response = await fetchImpl(`${base}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, redirect: 'error', credentials: 'omit' });
        let data;
        try { data = response.status === 204 ? null : await response.json(); }
        catch { throw new Error(`The configured API returned a non-JSON response (${response.status}). Check the API URL points to the MDT backend, not the web dashboard.`); }
        if (!response.ok) {
          const detail = data?.detail;
          const error = new Error(typeof detail === 'string' ? detail : detail?.message || `MDT request failed (${response.status})`);
          error.status = response.status;
          error.action = ({ 401: 'Copy a fresh MDT session token from Account and reconnect.', 403: 'Ask the project owner for an analyst account.', 404: 'Check the API URL and that this project or analysis still exists.', 409: 'Refresh the project after its import completes, then retry.', 429: 'The account or provider quota was reached. Retry after its reset.' })[response.status];
          throw error;
        }
        return data;
      } catch (error) {
        if (error.name === 'AbortError') throw new Error(signal?.aborted ? 'Request cancelled.' : 'MDT did not respond in time. The server may be waking; retry shortly.');
        throw error;
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
      }
    }
    return {
      request,
      projects: (options = {}) => request('/v1/projects', options).then(data => data.projects || []),
      analyze: (projectId, payload, idempotencyKey, options = {}) => request(`/v1/projects/${encodeURIComponent(projectId)}/analyses`, { ...options, method: 'POST', body: payload, idempotencyKey }),
      job: (jobId, options = {}) => request(`/v1/jobs/${encodeURIComponent(jobId)}`, options),
      cancel: jobId => request(`/v1/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' }),
    };
  }

  function resultSummary(envelope) {
    const result = envelope?.result || envelope || {};
    const format = value => ['number','string'].includes(typeof value) && String(value).trim() && Number.isFinite(Number(value)) ? Number(value).toFixed(3).replace(/\.?0+$/, '') : 'unavailable';
    const health = result.architecture_health || {};
    const partial = result.partial_results || ['partial','insufficient_communication_evidence'].includes(health.assessment_status);
    const assessment = health.assessment_status ? `Architecture assessment: ${health.assessment_status.replaceAll('_',' ')}\n` : '';
    const interpretation = health.interpretation || 'Recorded findings only; zero does not establish a debt-free or safe architecture.';
    return `Commit risk: ${format(result.risk_score)} / 100\nArchitectural debt: ${format(result.architecture_smell_score ?? health.score)} / 100\n${assessment}${interpretation}\nEvidence: ${result.evidence?.mode || 'not supplied'}\n${partial ? 'Partial coverage — review warnings.\n' : ''}${result.explanation || ''}`;
  }

  function webLink(webUrl, projectId, jobId) {
    const base = validateServerUrl(webUrl);
    return `${base}/#/workspace?${new URLSearchParams({ project: projectId, job: jobId })}`;
  }

  function errorMessage(error) {
    const message = error?.message || String(error);
    return error?.action ? `${message} ${error.action}` : message;
  }

  return { createClient, validateServerUrl, parseGitHubUrl, analysisPayload, resultSummary, webLink, errorMessage, isTerminal: status => TERMINAL.has(status) };
});
