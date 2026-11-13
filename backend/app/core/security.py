"""Security, Cryptography, and Token Management."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.errors import AuthenticationError


def hash_password(password: str) -> str:
    """Hash plain password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"iat": now, "exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create signed JWT refresh token."""
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"iat": now, "exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT token signature and expiration."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthenticationError("Invalid authentication token") from e


# --- Credential Encryption via Fernet ---
_fernet_instance: Fernet | None = None


def get_fernet() -> Fernet:
    """Initialize or return cached Fernet symmetric encryption cipher."""
    global _fernet_instance
    if _fernet_instance is None:
        try:
            _fernet_instance = Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))
        except Exception:
            # Fallback for dev if ENCRYPTION_KEY is invalid/empty: generate a valid key
            key = Fernet.generate_key()
            _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_secret(secret: str) -> str:
    """Encrypt sensitive string (e.g. database password/URI) using Fernet."""
    if not secret:
        return ""
    cipher = get_fernet()
    return cipher.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypt Fernet-encrypted string."""
    if not encrypted_secret:
        return ""
    cipher = get_fernet()
    try:
        return cipher.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError("Failed to decrypt secret with configured encryption key") from e
