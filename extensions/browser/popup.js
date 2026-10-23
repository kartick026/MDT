/* global chrome, MDTClient */
const element = id => document.getElementById(id);
let currentUrl = '';
let settings;
let connectionId;
let lastJob;
let pollTimer;
let pollingFailures = 0;
let generation = 0;
let hasProjects = false;

async function send(message) {
  const response = await chrome.runtime.sendMessage({ connectionId, ...message });
  if (!response?.ok) {
    const error = new Error(response?.error || 'MDT extension did not respond.');
    error.status = response?.status;
    throw error;
  }
  return response.data;
}
function showError(error) { element('error').textContent = error.message || String(error); }
function status(value) { element('status').textContent = value; element('error').textContent = ''; }
function clearConnectionView() {
  clearTimeout(pollTimer);
  connectionId = undefined;
  lastJob = undefined;
  hasProjects = false;
  pollingFailures = 0;
  element('connected').hidden = true;
  element('result').hidden = true;
  element('summary').textContent = '';
  element('open-web').removeAttribute('href');
  element('analyze').disabled = true;
}
function setProjects(projects) {
  element('project').replaceChildren();
  for (const project of projects) {
    const option = document.createElement('option');
    option.value = project.id;
    option.textContent = `${project.name}${project.ready === false ? ' (importing)' : ''}`;
    element('project').append(option);
    if (currentUrl.startsWith(project.repo_url.replace(/\.git$/, '') + '/') || currentUrl === project.repo_url) element('project').value = project.id;
  }
  hasProjects = projects.length > 0;
  element('analyze').disabled = !hasProjects || !currentUrl;
  if (!projects.length) status('Create a project in the MDT web workspace, then reconnect.');
}
async function refresh() {
  clearTimeout(pollTimer);
  const active = generation;
  const saved = lastJob;
  const destination = settings;
  if (!saved || !connectionId) { status('No job yet.'); return; }
  try {
    const job = await send({ type: 'job', jobId: saved.jobId });
    if (active !== generation || saved !== lastJob) return;
    pollingFailures = 0;
    element('result').hidden = false;
    element('summary').textContent = job.result ? MDTClient.resultSummary(job) : `Status: ${job.status}\n${job.stage || 'Waiting for the server'}`;
    element('open-web').href = MDTClient.webLink(destination.webUrl, saved.projectId, saved.jobId);
    element('cancel').hidden = MDTClient.isTerminal(job.status);
    status(`Analysis ${job.status}`);
    if (job.error) showError(typeof job.error === 'string' ? new Error(job.error) : new Error(JSON.stringify(job.error)));
    if (!MDTClient.isTerminal(job.status)) pollTimer = setTimeout(refresh, 3000);
  } catch (error) {
    if (active !== generation || saved !== lastJob) return;
    showError(error);
    pollingFailures += 1;
    if (![401,403,404,409].includes(error.status) && pollingFailures < 4) pollTimer = setTimeout(refresh, 5000);
  }
}
async function restore(active, fillDefaults = false) {
  const state = await send({ type: 'state' });
  if (active !== generation) return;
  settings = state.settings;
  connectionId = state.connectionId;
  lastJob = state.lastJob;
  if (fillDefaults) {
    element('api-url').value = settings?.baseUrl || '';
    element('web-url').value = settings?.webUrl || '';
  }
  element('connection').open = !state.connected;
  element('connected').hidden = !state.connected;
  if (state.connected) {
    const response = await send({ type: 'projects' });
    if (active !== generation) return;
    setProjects(response.projects);
    if (lastJob) await refresh();
  }
}
element('connect-form').addEventListener('submit', async event => {
  event.preventDefault();
  const active = ++generation;
  clearConnectionView();
  try {
    const baseUrl = MDTClient.validateServerUrl(element('api-url').value);
    const webUrl = MDTClient.validateServerUrl(element('web-url').value);
    const token = element('token').value;
    const url = new URL(baseUrl);
    const origin = `${url.protocol}//${url.hostname}/*`;
    const allowed = await chrome.permissions.request({ origins: [origin] });
    if (active !== generation) return;
    if (!allowed) throw new Error('Permission for this MDT server was not granted.');
    status('Connecting…');
    const response = await send({ type: 'connect', baseUrl, webUrl, token });
    if (active !== generation) return;
    settings = response.settings;
    connectionId = response.connectionId;
    element('token').value = '';
    element('connected').hidden = false;
    element('connection').open = false;
    setProjects(response.projects);
    if (hasProjects) status('Connected. Choose a matching project and analyze.');
  } catch (error) {
    if (active !== generation) return;
    try { await restore(active); } catch { /* Preserve the original connection error. */ }
    if (active === generation) showError(error);
  }
});
element('analyze').addEventListener('click', async () => {
  const active = generation;
  element('analyze').disabled = true;
  try {
    status('Submitting analysis…');
    const submitted = await send({ type: 'analyze', url: currentUrl, projectId: element('project').value, requestId: crypto.randomUUID() });
    if (active !== generation) return;
    lastJob = submitted;
    await refresh();
  } catch (error) { if (active === generation) showError(error); }
  finally { if (active === generation) element('analyze').disabled = !hasProjects || !currentUrl; }
});
element('refresh').addEventListener('click', () => { pollingFailures = 0; refresh(); });
element('cancel').addEventListener('click', async () => {
  const active = generation;
  if (!lastJob) return;
  try { await send({ type: 'cancel', jobId: lastJob.jobId }); if (active === generation) await refresh(); }
  catch (error) { if (active === generation) showError(error); }
});
element('disconnect').addEventListener('click', async () => {
  const active = ++generation;
  clearConnectionView();
  element('connection').open = true;
  try {
    await send({ type: 'disconnect' });
    if (active === generation) status('Disconnected. Your saved session and job have been removed.');
  } catch (error) { if (active === generation) showError(error); }
});
(async () => {
  const active = generation;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (active !== generation) return;
    try { const context = MDTClient.parseGitHubUrl(tab?.url || ''); currentUrl = tab.url; element('page-context').textContent = context.repo_url; }
    catch { element('page-context').textContent = 'Open a GitHub repository, commit, comparison, or pull request first.'; }
    await restore(active, true);
  } catch (error) { if (active === generation) showError(error); }
})();
