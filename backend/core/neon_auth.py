"""Verify Neon identity cryptographically before looking up its user profile."""
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import HTTPException
import jwt

from core.config import settings


@lru_cache(maxsize=4)
def _jwks_client(url):
    return jwt.PyJWKClient(url, timeout=10, cache_keys=True)


def verified_neon_identity(token):
    auth = urlsplit(settings.NEON_AUTH_URL)
    jwks = urlsplit(settings.NEON_JWKS_URL)
    if auth.scheme != 'https' or not auth.hostname or jwks.scheme != 'https' or not jwks.hostname:
        raise HTTPException(503, 'Neon sign-in is not configured')
    issuer = f'{auth.scheme}://{auth.netloc}'
    try:
        key = _jwks_client(settings.NEON_JWKS_URL).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=['EdDSA', 'RS256', 'ES256'], issuer=issuer,
                            options={'require': ['exp', 'iat', 'iss', 'sub'], 'verify_aud': False})
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, 'Identity provider is temporarily unavailable') from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, 'Invalid or expired provider token') from exc
    subject = claims['sub']
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise HTTPException(401, 'Invalid provider identity')
    # A valid signature is necessary but does not imply a verified human account.
    # Never infer a user from session timestamps, email prefixes or client input.
    from core.store import get_store
    store = get_store()
    if not store.postgres:
        raise HTTPException(503, 'Neon identity storage is unavailable')
    try:
        with store.connection() as db:
            row = db.execute('SELECT id, name, email, image, "emailVerified" FROM neon_auth."user" WHERE id=?', (subject,)).fetchone()
    except Exception as exc:
        raise HTTPException(503, 'Identity storage is temporarily unavailable') from exc
    if not row or not row['emailVerified'] or not row['email']:
        raise HTTPException(401, 'A verified provider account is required')
    return issuer, subject, dict(row)
