"""Single-user authentication — PBKDF2 password hash + HMAC-signed session cookie."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request, Response

logger = logging.getLogger(__name__)

_AUTH_FILE       = Path(__file__).parent.parent / "auth.json"
_COOKIE_NAME     = "naa_session"
_SESSION_MAX_AGE = 7 * 24 * 3600   # 7 days
_PBKDF2_ITERS    = 260_000


def _load() -> dict:
    try:
        return json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    try:
        _AUTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("Could not save auth file: %s", exc)


def is_setup_done() -> bool:
    return bool(_load().get("password_hash"))


def _secret_key() -> bytes:
    data = _load()
    if "secret_key" not in data:
        data["secret_key"] = secrets.token_hex(32)
        _save(data)
    return bytes.fromhex(data.get("secret_key", secrets.token_hex(32)))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERS)
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk_hex = stored.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERS)
        return hmac.compare_digest(dk_hex, expected.hex())
    except Exception:
        return False


def setup_password(password: str) -> None:
    data = _load()
    data["password_hash"] = hash_password(password)
    _save(data)


def check_password(password: str) -> bool:
    return verify_password(password, _load().get("password_hash", ""))


def make_session_cookie() -> str:
    ts      = str(int(time.time()))
    payload = f"admin:{ts}"
    sig     = hmac.new(_secret_key(), payload.encode(), "sha256").hexdigest()
    return f"{base64.b64encode(payload.encode()).decode()}:{sig}"


def verify_session_cookie(value: str) -> bool:
    try:
        enc, sig = value.rsplit(":", 1)
        payload  = base64.b64decode(enc).decode()
        expected = hmac.new(_secret_key(), payload.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        _, ts = payload.split(":", 1)
        return (time.time() - int(ts)) < _SESSION_MAX_AGE
    except Exception:
        return False


def set_session(response: Response) -> None:
    response.set_cookie(
        _COOKIE_NAME, make_session_cookie(),
        httponly=True, samesite="lax", max_age=_SESSION_MAX_AGE,
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME)


def is_authenticated(request: Request) -> bool:
    cookie = request.cookies.get(_COOKIE_NAME, "")
    return bool(cookie and verify_session_cookie(cookie))


def require_auth(request: Request) -> None:
    """FastAPI dependency — raises HTTP 401 if session cookie is missing or invalid."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
