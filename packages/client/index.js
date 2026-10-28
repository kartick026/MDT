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

  function coverageSummary(result) {
    const count = value => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
    const first = (...values) => values.map(count).find(value => value !== null) ?? null;
    const topologyLike = value => value && ['indicators', 'candidate_files', 'files_candidates', 'parsers'].some(key => Object.hasOwn(value, key));
    const coverage = result.topology_coverage || result.evidence?.topology_coverage || result.snapshot?.coverage || (topologyLike(result.coverage) ? result.coverage : {}) || {};
    const source = coverage.indicators?.source_scan || {};
    const parser = coverage.indicators?.parser_support || {};
    const read = first(source.read_files, coverage.files_read);
    const attempted = first(source.attempted_files, coverage.files_attempted);
    const eligible = first(source.eligible_files, coverage.candidate_files, coverage.files_candidates);
    const parserRead = first(parser.read_files, read);
    const hasModes = coverage.parsers && Object.keys(coverage.parsers).length > 0;
    const parsed = first(parser.parsed_files, hasModes ? (count(coverage.parsers.ast) ?? 0) + (count(coverage.parsers.tree_sitter) ?? 0) : null);
    const heuristic = first(parser.heuristic_files, hasModes ? count(coverage.parsers.heuristic ?? 0) : null);
    const failed = first(parser.failed_files, hasModes ? count(coverage.parsers.failed ?? 0) : null);
    const partial = first(parser.partial_files, hasModes ? count(coverage.parsers.partial ?? 0) : null);
    const unclassified = first(parser.unclassified_files);
    const scanInconsistent = (eligible !== null && read !== null && read > eligible) || (attempted !== null && read !== null && attempted < read)
      || (attempted !== null && eligible !== null && attempted > eligible) || source.reasons?.includes('source_scan_counts_inconsistent');
    const parserInconsistent = parser.reasons?.includes('parser_counts_inconsistent') || (hasModes && Object.values(coverage.parsers).some(value => count(value) === null))
      || (parserRead !== null && ((read !== null && parserRead !== read)
      || [parsed, heuristic, failed, partial, unclassified].reduce((sum, value) => sum + (value ?? 0), 0) > parserRead));
    const demo = result.status === 'demo' || result.evidence?.mode === 'illustrative_demo';
    const runtimeStatus = coverage.indicators?.runtime_verification?.status;
    const noRuntime = runtimeStatus === 'not_measured' || (!runtimeStatus && (coverage.source === 'static_source' || result.architecture_health?.evidence?.runtime_traffic_measured === false || demo));
    const sourceText = scanInconsistent ? 'Inconsistent recorded counts; completeness unavailable' : read !== null && eligible !== null ? `${read} / ${eligible} eligible mapped source files read` : 'Not recorded';
    const parserText = parserInconsistent ? 'Inconsistent recorded counts; completeness unavailable' : parsed !== null && parserRead !== null ? `${parsed} / ${parserRead} read files syntax parsed` : 'Not recorded';
    const breakdown = heuristic !== null ? ` (${heuristic} heuristic; ${failed ?? 'unknown'} failed; ${partial ?? 'unknown'} partial)` : '';
    const recorded = !coverage.indicators && Object.keys(coverage).length > 0 ? '\nCounts come from the saved capture; re-import to apply scanner updates.' : '';
    return `Source scan: ${sourceText}\nParser support: ${parserText}${breakdown}\nRuntime verification: ${noRuntime ? 'Not measured' : 'Not recorded'}\nFile counts do not establish complete architecture or runtime coverage.${recorded}${demo ? '\nIllustrative demo topology; no repository-wide source scan is claimed.' : ''}`;
  }

  function resultSummary(envelope) {
    const result = envelope?.result || envelope || {};
    const format = value => ['number','string'].includes(typeof value) && String(value).trim() && Number.isFinite(Number(value)) ? Number(value).toFixed(3).replace(/\.?0+$/, '') : 'unavailable';
    const health = result.architecture_health || {};
    const partial = result.partial_results || ['partial','insufficient_communication_evidence'].includes(health.assessment_status);
    const assessment = health.assessment_status ? `Architecture assessment: ${health.assessment_status.replaceAll('_',' ')}\n` : '';
    const interpretation = health.interpretation || 'Recorded findings only; zero does not establish a debt-free or safe architecture.';
    return `Commit risk: ${format(result.risk_score)} / 100\nArchitectural debt: ${format(result.architecture_smell_score ?? health.score)} / 100\n${assessment}${interpretation}\nEvidence: ${result.evidence?.mode || 'not supplied'}\n${coverageSummary(result)}\n${partial ? 'Limited evidence — review assessment warnings.\n' : ''}${result.explanation || ''}`;
  }

  function webLink(webUrl, projectId, jobId) {
    const base = validateServerUrl(webUrl);
    return `${base}/#/workspace?${new URLSearchParams({ project: projectId, job: jobId })}`;
  }

  function errorMessage(error) {
    const message = error?.message || String(error);
    return error?.action ? `${message} ${error.action}` : message;
  }

  return { createClient, validateServerUrl, parseGitHubUrl, analysisPayload, resultSummary, coverageSummary, webLink, errorMessage, isTerminal: status => TERMINAL.has(status) };
});
