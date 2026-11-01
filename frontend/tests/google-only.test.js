import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { fileURLToPath } from 'node:url';

test('the account form offers Google without password or seeded credential controls', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom' });
  try {
    const { SignInForm } = await server.ssrLoadModule('/src/components/AuthPage.jsx');
    const { AuthContext } = await server.ssrLoadModule('/src/context/useAuth.js');
    const html = renderToStaticMarkup(React.createElement(AuthContext.Provider,
      { value: { loginOAuth: async () => {} } }, React.createElement(SignInForm)));
    assert.match(html, /Continue with Google/);
    assert.doesNotMatch(html, /type="password"|admin123|Fill Admin|Username|Create account|sign in with password/);
    assert.equal((html.match(/<button/g) || []).length, 1);
  } finally {
    await server.close();
  }
});
