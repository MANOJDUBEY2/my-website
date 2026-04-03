"""
auth.py – JWT Authentication & Password Hashing for PawVibe
────────────────────────────────────────────────────────────
Handles:
  - Password hashing with Bcrypt (via passlib)
  - JWT access token creation and validation
  - JWT refresh token creation and validation
  - FastAPI dependency: get_current_user
  - FastAPI dependency: require_admin
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from . import models

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE-THIS-IN-PRODUCTION-USE-OPENSSL-RAND-HEX-32")
ALGORITHM: str  = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS: int    = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# ── Password Hashing Setup ───────────────────────────────────────────────────
# bcrypt with cost factor 12 (strong, ~250ms per hash — industry standard)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,    # Higher = more secure but slower; 12 is the sweet spot
)

# ── HTTP Bearer token extractor ───────────────────────────────────────────────
# auto_error=False means we handle missing tokens gracefully
bearer_scheme = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────────────────────
# Password Utilities
# ─────────────────────────────────────────────────────────────────────────────

def get_password_hash(password: str) -> str:
    """Hash a plaintext password using Bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against its Bcrypt hash.
    Returns True if they match, False otherwise.
    Uses constant-time comparison to prevent timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ─────────────────────────────────────────────────────────────────────────────
# JWT Token Creation
# ─────────────────────────────────────────────────────────────────────────────

def create_access_token(
    user_id: int,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a short-lived JWT access token.

    Payload claims:
      sub  → user email (standard JWT subject)
      uid  → user id (for quick DB lookups)
      role → user role (customer | admin) for authorization checks
      type → 'access' (to differentiate from refresh tokens)
      exp  → expiry timestamp
      iat  → issued-at timestamp
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub":  email,
        "uid":  user_id,
        "role": role,
        "type": "access",
        "exp":  expire,
        "iat":  datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    user_id: int,
    email: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a long-lived JWT refresh token.
    Refresh tokens have minimal claims (no role — fetch fresh from DB on refresh).

    Payload claims:
      sub  → user email
      uid  → user id
      type → 'refresh' (must be validated to prevent using refresh as access)
      exp  → expiry (default 7 days)
      iat  → issued-at
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub":  email,
        "uid":  user_id,
        "type": "refresh",
        "exp":  expire,
        "iat":  datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_token_pair(user: "models.User") -> dict:
    """
    Convenience function: create both access and refresh tokens for a user.
    Returns a dict matching the TokenResponse schema.
    """
    access_token  = create_access_token(user.id, user.email, user.role)
    refresh_token = create_refresh_token(user.id, user.email)
    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
    }


# ─────────────────────────────────────────────────────────────────────────────
# JWT Token Verification
# ─────────────────────────────────────────────────────────────────────────────

def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Raises HTTPException on invalid/expired tokens.
    Returns the decoded payload dict.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_refresh_token(token: str) -> dict:
    """
    Verify a refresh token specifically.
    Ensures the 'type' claim is 'refresh' to prevent misuse.
    """
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token.",
        )
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ─────────────────────────────────────────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> "models.User":
    """
    FastAPI dependency: extract and validate the Bearer token,
    then fetch and return the corresponding User from the database.

    Usage:
        @router.get("/me")
        def get_me(current_user: models.User = Depends(get_current_user)):
            return current_user
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)

    # Ensure it's an access token (not accidentally using a refresh token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected access token.",
        )

    user_id: Optional[int] = payload.get("uid")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is malformed.",
        )

    # Fetch fresh user from DB (catches deleted/deactivated accounts)
    from . import crud
    user = crud.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated.",
        )

    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional["models.User"]:
    """
    Like get_current_user but returns None instead of raising for unauthenticated requests.
    Useful for endpoints that behave differently for logged-in vs. anonymous users.
    """
    if not credentials or not credentials.credentials:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


def require_admin(
    current_user: "models.User" = Depends(get_current_user),
) -> "models.User":
    """
    FastAPI dependency: ensure the current user has the 'admin' role.
    Raises 403 Forbidden if the user is not an admin.

    Usage:
        @router.delete("/products/{id}")
        def delete_product(admin: models.User = Depends(require_admin)):
            ...
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. You do not have permission.",
        )
    return current_user
