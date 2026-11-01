import test from 'node:test';
import assert from 'node:assert/strict';

test('real Neon SDK exchanges its session JWT and never trusts an opaque token or profile', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' });
  const originalFetch = globalThis.fetch;
  const originalStorage = globalThis.sessionStorage;
  const signedToken = 'test-header.test-payload.test-signature';
  const providerCalls = [], exchanged = [];
  let includeJwt = true;
  globalThis.sessionStorage = { getItem: () => null };
  globalThis.fetch = async input => {
    const url = String(input);
    providerCalls.push(url);
    if (url.endsWith('/sign-out')) return Response.json({ success: true });
    assert.match(url, /^https:\/\/provider\.example\/auth\/get-session/);
    return Response.json({ session: { id: 'session-id', token: 'opaque-session-secret' }, user: { id: 'provider-subject', email: 'user@example.com' } },
      { headers: includeJwt ? { 'set-auth-jwt': signedToken } : {} });
  };
  try {
    const { default: api } = await server.ssrLoadModule('/src/api.js');
    api.defaults.adapter = async config => {
      if (config.url === '/auth/oauth/config') return { config, status: 200, data: { enabled: true, auth_url: 'https://provider.example/auth' }, headers: {} };
      assert.equal(config.url, '/auth/oauth-login');
      const payload = JSON.parse(config.data);
      exchanged.push(payload);
      assert.deepEqual(payload, { id_token: signedToken });
      return { config, status: 200, data: { access_token: 'application-token', user: { username: 'bound-owner', role: 'viewer' } }, headers: {} };
    };
    const bridge = await server.ssrLoadModule('/src/utils/neonAuth.js');
    assert.equal((await bridge.exchangeNeonSession()).user.username, 'bound-owner');
    assert.equal(exchanged.length, 1);
    await bridge.signOutNeon();
    includeJwt = false;
    await assert.rejects(bridge.exchangeNeonSession(), /signed token/);
    assert.equal(exchanged.length, 1, 'No app login occurs without a provider JWT');
    assert.ok(providerCalls.every(url => !url.endsWith('/token')), 'Uses SDK session JWT handling rather than an unsupported endpoint');
  } finally {
    globalThis.fetch = originalFetch;
    if (originalStorage === undefined) delete globalThis.sessionStorage;
    else globalThis.sessionStorage = originalStorage;
    await server.close();
  }
});
