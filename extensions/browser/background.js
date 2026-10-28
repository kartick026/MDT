/* global importScripts, chrome, MDTClient */
importScripts('client.js');

// One session record binds the credential to its destination. Local storage
// contains UI defaults only; it is never used to route an authenticated request.
let connection;
let epoch = 0;
let writes = Promise.resolve();
const ready = (async () => {
  connection = (await chrome.storage.session.get('connection')).connection;
  // Older releases paired URL/token separately. Require reconnect after upgrade.
  await chrome.storage.session.remove(['token', 'lastJob']);
})();
const changed = () => new Error('The MDT connection changed. Reopen the popup or reconnect before retrying.');
function serialize(action) {
  const result = writes.then(action);
  writes = result.catch(() => {});
  return result;
}
function assertCurrent(session, generation) {
  if (epoch !== generation || connection?.id !== session.id) throw changed();
}
async function persist(session, generation) {
  const previous = connection;
  await chrome.storage.session.set({ connection: session });
  if (generation !== epoch) {
    if (previous) await chrome.storage.session.set({ connection: previous });
    else await chrome.storage.session.remove('connection');
    throw changed();
  }
  connection = session;
}
async function snapshot(message) {
  await ready;
  const session = connection;
  if (!session?.token) throw new Error('Connect to MDT with your short-lived session token first.');
  if (message.connectionId !== session.id) throw changed();
  return { session, generation: epoch, api: MDTClient.createClient({ baseUrl: session.baseUrl, token: session.token }) };
}
const publicState = session => ({
  connected: Boolean(session), connectionId: session?.id,
  ...(session ? { settings: { baseUrl: session.baseUrl, webUrl: session.webUrl }, lastJob: session.lastJob } : {}),
});

async function handle(message) {
  if (message.type === 'connect') {
    const generation = ++epoch;
    const baseUrl = MDTClient.validateServerUrl(message.baseUrl);
    const webUrl = MDTClient.validateServerUrl(message.webUrl);
    const token = String(message.token || '').trim();
    if (!token || token.length > 8192) throw new Error('Enter a valid MDT session token.');
    const projects = await MDTClient.createClient({ baseUrl, token }).projects();
    await ready;
    return serialize(async () => {
      if (generation !== epoch) throw changed();
      const session = { id: crypto.randomUUID(), baseUrl, webUrl, token };
      await persist(session, generation);
      await chrome.storage.local.set({ settings: { baseUrl, webUrl } });
      if (generation !== epoch) throw changed();
      return { ...publicState(session), projects };
    });
  }
  if (message.type === 'disconnect') {
    ++epoch;
    await ready;
    return serialize(async () => {
      connection = undefined;
      await chrome.storage.session.clear();
      return { disconnected: true };
    });
  }
  if (message.type === 'state') {
    await ready;
    await writes;
    const defaults = (await chrome.storage.local.get('settings')).settings;
    return { settings: defaults, ...publicState(connection) };
  }
  const { session, generation, api } = await snapshot(message);
  if (message.type === 'projects') {
    const projects = await api.projects();
    assertCurrent(session, generation);
    return { projects };
  }
  if (message.type === 'analyze') {
    const context = MDTClient.parseGitHubUrl(message.url);
    const projects = await api.projects();
    assertCurrent(session, generation);
    const project = projects.find(item => item.id === message.projectId);
    if (!project) throw new Error('Select an accessible project.');
    if (project.ready === false) throw new Error('This project is still importing. Open the web workspace to check progress.');
    const payload = MDTClient.analysisPayload(context, project);
    const job = await api.analyze(project.id, payload, message.requestId);
    if (generation !== epoch || session.id !== connection?.id) {
      await api.cancel(job.job_id).catch(() => {});
      throw new Error('The connection changed during submission. Cancellation was attempted on the original server; check its History for the final state.');
    }
    const lastJob = { jobId: job.job_id, projectId: project.id };
    try {
      return await serialize(async () => {
        assertCurrent(session, generation);
        await persist({ ...session, lastJob }, generation);
        return { ...lastJob, status: job.status };
      });
    } catch (error) {
      if (generation !== epoch) await api.cancel(job.job_id).catch(() => {});
      throw error;
    }
  }
  if (message.type === 'job' || message.type === 'cancel') {
    const result = await (message.type === 'job' ? api.job(message.jobId) : api.cancel(message.jobId));
    assertCurrent(session, generation);
    return result;
  }
  throw new Error('Unsupported MDT command.');
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(''))) return false;
  handle(message).then(data => respond({ ok: true, data })).catch(error => respond({ ok: false, error: MDTClient.errorMessage(error), status: error.status }));
  return true;
});
