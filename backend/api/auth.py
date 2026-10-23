"""
MDT Authentication API Endpoints
Login, Token issuance, User identity, and Token refresh.
"""
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from core.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
    decode_access_token,
    oauth2_scheme,
    require_admin,
)
from core.config import settings
from core.utils import check_rate_limit
from schemas.auth import Token, UserLogin, UserOut, UserRegistration

router = APIRouter()
logger = logging.getLogger("mdt.api.auth")


def _issue_token(user: UserOut) -> Token:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=expires_delta,
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.post("/login", response_model=Token, summary="User login with JSON credentials")
def login_json(credentials: UserLogin, request: Request):
    """Authenticate user with username and password, returning a JWT bearer token."""
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip, settings.RATE_LIMIT_LOGIN_PER_MINUTE, window_seconds=60, scope="login"):
        logger.warning("Login rate limit exceeded for client IP %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again shortly.",
            headers={"Retry-After": "60"},
        )

    user = authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("User logged in successfully: %s (role=%s)", user.username, user.role)
    return _issue_token(user)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED, summary="Create a viewer account")
def register(credentials: UserRegistration, request: Request):
    """Create a self-service read-only account and start a session."""
    if not settings.ALLOW_SELF_SIGNUP:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Self-service signup is disabled.")
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip, settings.RATE_LIMIT_LOGIN_PER_MINUTE, window_seconds=60, scope="signup"):
        raise HTTPException(status_code=429, detail="Too many signup attempts")
    try:
        user = register_user(credentials.username, credentials.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info("Viewer account created: %s", user.username)
    return _issue_token(user)


@router.post("/token", response_model=Token, summary="OAuth2 standard form login (Swagger UI compatible)")
def login_form(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 compatible token login for documentation and OpenAPI client generators."""
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip, settings.RATE_LIMIT_LOGIN_PER_MINUTE, window_seconds=60, scope="login"):
        logger.warning("Login form rate limit exceeded for client IP %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again shortly.",
            headers={"Retry-After": "60"},
        )

    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _issue_token(user)


@router.get("/me", response_model=UserOut, summary="Get current user profile")
async def read_current_user(current_user: UserOut = Depends(get_current_user)):
    """Retrieve identity of currently authenticated user."""
    return current_user


@router.post("/refresh", response_model=Token, summary="Refresh existing JWT access token")
def refresh_token(current_user: UserOut = Depends(get_current_user), token: str = Depends(oauth2_scheme)):
    """Issue a fresh JWT token for an already authenticated active user session."""
    result = _issue_token(current_user)
    _revoke(token)
    return result


def _revoke(token):
    if token:
        from core.store import get_store
        payload = decode_access_token(token)
        get_store().put("revoked", payload["jti"], "auth", {"expires": payload["exp"]})


@router.post("/logout", status_code=204)
def logout(current_user: UserOut = Depends(get_current_user), token: str = Depends(oauth2_scheme)):
    _revoke(token)


@router.post("/invite", response_model=UserOut, status_code=201)
def invite(credentials: UserRegistration, current_user: UserOut = Depends(require_admin)):
    """Provision a private-beta analyst; hand credentials to the user separately."""
    try:
        return register_user(credentials.username, credentials.password, role="analyst")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
