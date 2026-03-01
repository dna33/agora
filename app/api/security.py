import hmac
import hashlib

from fastapi import Cookie, Header, HTTPException, Query

from app.core.config import get_settings


def _is_valid_admin_key(candidate: str | None) -> bool:
    settings = get_settings()
    if not settings.admin_api_key or not candidate:
        return False
    return hmac.compare_digest(candidate, settings.admin_api_key)


def is_valid_admin_api_key(candidate: str | None) -> bool:
    return _is_valid_admin_key(candidate)


def issue_admin_session_token() -> str:
    settings = get_settings()
    if not settings.admin_api_key:
        return ""
    seed = "agora-admin-session-v1"
    return hmac.new(
        settings.admin_api_key.encode("utf-8"),
        seed.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _is_valid_admin_session_token(token: str | None) -> bool:
    if not token:
        return False
    expected = issue_admin_session_token()
    return bool(expected and hmac.compare_digest(token, expected))


def require_admin_api_key(x_admin_api_key: str | None = Header(default=None, alias="X-Admin-Api-Key")) -> None:
    settings = get_settings()

    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin authentication not configured")

    if not _is_valid_admin_key(x_admin_api_key):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_admin_api_key_header_or_query(
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-Api-Key"),
    admin_api_key: str | None = Query(default=None),
) -> None:
    settings = get_settings()

    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin authentication not configured")

    candidate = x_admin_api_key or admin_api_key
    if not _is_valid_admin_key(candidate):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_admin_api_key_header_or_cookie(
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-Api-Key"),
    admin_session: str | None = Cookie(default=None),
) -> None:
    settings = get_settings()

    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin authentication not configured")

    if _is_valid_admin_key(x_admin_api_key):
        return
    if _is_valid_admin_session_token(admin_session):
        return

    raise HTTPException(status_code=403, detail="Forbidden")


def require_admin_api_key_query_or_cookie(
    admin_api_key: str | None = Query(default=None),
    admin_session: str | None = Cookie(default=None),
) -> None:
    settings = get_settings()

    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin authentication not configured")

    if _is_valid_admin_key(admin_api_key):
        return
    if _is_valid_admin_session_token(admin_session):
        return

    raise HTTPException(status_code=403, detail="Forbidden")
