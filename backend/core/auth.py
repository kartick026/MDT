"""
MDT Core Authentication & JWT Security Module
Handles password hashing, token issuance, decoding, and FastAPI dependencies.
"""
import logging
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.config import settings
from schemas.auth import UserOut, TokenPayload

logger = logging.getLogger("mdt.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

# In-memory user credentials registry (seeded from environment)
# Maps username -> { "password_hash": str, "role": str, "is_active": bool }
_USERS_DB: Dict[str, Dict[str, Any]] = {}
_REGISTERED_USERS: set[str] = set()
_USERS_LOCK = threading.Lock()
_USERS_INITIALIZED = False
USERS_FILE = Path(__file__).parent.parent / "data" / "users.json"


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as exc:
        logger.warning("Password verification failed with error: %s", exc)
        return False


def _init_default_users():
    """Load persisted viewer accounts and seed the development identities."""
    global _USERS_INITIALIZED
    with _USERS_LOCK:
        if _USERS_INITIALIZED:
            return

        if USERS_FILE.exists():
            try:
                accounts = json.loads(USERS_FILE.read_text(encoding="utf-8"))
                if isinstance(accounts, list):
                    for account in accounts:
                        username = account.get("username") if isinstance(account, dict) else None
                        password_hash = account.get("password_hash") if isinstance(account, dict) else None
                        if username and password_hash:
                            _USERS_DB[username] = {
                                "password_hash": password_hash,
                                "role": "viewer",
                                "is_active": bool(account.get("is_active", True)),
                            }
                            _REGISTERED_USERS.add(username)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Unable to load registered users: %s", exc)

        admin_user = settings.ADMIN_USERNAME.strip()
        if admin_user not in _USERS_DB:
            _USERS_DB[admin_user] = {
                "password_hash": hash_password(settings.ADMIN_PASSWORD.strip()),
                "role": "admin",
                "is_active": True,
            }
        if settings.ENABLE_DEFAULT_VIEWER:
            auditor_user = settings.AUDITOR_USERNAME.strip()
            if auditor_user and auditor_user not in _USERS_DB:
                _USERS_DB[auditor_user] = {
                    "password_hash": hash_password(settings.AUDITOR_PASSWORD.strip()),
                    "role": "viewer",
                    "is_active": True,
                }
        _USERS_INITIALIZED = True


def _persist_registered_users() -> None:
    """Persist only self-registered viewer accounts, never default admin credentials."""
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    accounts = [
        {
            "username": username,
            "password_hash": _USERS_DB[username]["password_hash"],
            "is_active": _USERS_DB[username].get("is_active", True),
        }
        for username in sorted(_REGISTERED_USERS)
        if username in _USERS_DB
    ]
    temporary_file = USERS_FILE.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    temporary_file.replace(USERS_FILE)


def register_user(username: str, plain_password: str) -> UserOut:
    """Create a durable viewer account without allowing privilege escalation."""
    _init_default_users()
    cleaned_username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,100}", cleaned_username):
        raise ValueError("Username must be 3–100 characters using letters, numbers, '.', '_' or '-'.")
    if len(plain_password) < 8:
        raise ValueError("Password must contain at least 8 characters.")

    with _USERS_LOCK:
        if cleaned_username in _USERS_DB:
            raise ValueError("That username is already in use.")
        _USERS_DB[cleaned_username] = {
            "password_hash": hash_password(plain_password),
            "role": "viewer",
            "is_active": True,
        }
        _REGISTERED_USERS.add(cleaned_username)
        _persist_registered_users()

    return UserOut(username=cleaned_username, role="viewer", is_active=True)


# Initialize default user
_init_default_users()


def authenticate_user(username: str, plain_password: str) -> Optional[UserOut]:
    """Verify credentials and return user model or None."""
    _init_default_users()
    user_record = _USERS_DB.get(username)
    if not user_record:
        return None

    if not verify_password(plain_password, user_record["password_hash"]):
        return None

    if not user_record.get("is_active", True):
        return None

    return UserOut(
        username=username,
        role=user_record.get("role", "viewer"),
        is_active=True
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate a signed HS256 JWT access token.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp())
    })

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    Raises HTTPException on expiry or signature failure.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[UserOut]:
    """
    Extract a user from a Bearer JWT token.
    Returns None if neither is present or valid.
    """
    if not token:
        return None

    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub")
        if not username:
            return None
        role: str = payload.get("role", "viewer")
        return UserOut(username=username, role=role, is_active=True)
    except HTTPException:
        raise
    except Exception:
        return None


async def get_current_user(
    current_user: Optional[UserOut] = Depends(get_current_user_optional)
) -> UserOut:
    """
    Strict dependency: Requires a valid authenticated user.
    """
    if not settings.AUTH_REQUIRED:
        return UserOut(username=settings.ADMIN_USERNAME, role="admin", is_active=True)

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided or are invalid",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return current_user


async def require_admin(
    current_user: UserOut = Depends(get_current_user)
) -> UserOut:
    """
    Role check: Requires admin privileges.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires administrator privileges"
        )
    return current_user
