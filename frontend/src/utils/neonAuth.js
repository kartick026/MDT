import { getOAuthConfig, loginWithOAuth } from '../api';

let clientPromise;

async function getClient() {
  if (!clientPromise) {
    clientPromise = Promise.all([getOAuthConfig(), import('@neondatabase/auth')])
      .then(([config, sdk]) => {
        if (!config.enabled || !config.auth_url) throw new Error('Social sign-in is not configured. Use your password to sign in.');
        // This SDK wrapper retrieves the JWT injected into provider session
        // responses; the plain Better Auth /token endpoint is not universal.
        return sdk.createInternalNeonAuth(config.auth_url);
      }).catch(error => { clientPromise = undefined; throw error; });
  }
  return clientPromise;
}

export async function startNeonSignIn(provider = 'google') {
  const client = await getClient();
  sessionStorage.setItem('mdt_oauth_pending', String(Date.now()));
  const result = await client.adapter.signIn.social({ provider, callbackURL: window.location.href });
  if (result.error) {
    sessionStorage.removeItem('mdt_oauth_pending');
    throw new Error(result.error.message || 'Social sign-in failed.');
  }
  return result;
}

export async function exchangeNeonSession() {
  const client = await getClient();
  // The SDK consumes the verifier with its provider challenge cookie. Never
  // send an unverified email/profile to the application authentication API.
  const session = await client.adapter.getSession();
  if (session.error) throw new Error(session.error.message || 'Provider session could not be verified.');
  if (!session.data?.user) throw new Error('Social sign-in did not return a session. Please try again.');
  const signedToken = await client.getJWTToken();
  if (!signedToken || signedToken.split('.').length !== 3) throw new Error('Provider could not issue a signed token. Please sign in again.');
  return loginWithOAuth({ id_token: signedToken });
}

export async function signOutNeon() {
  const client = await getClient();
  await client.adapter.signOut();
}
