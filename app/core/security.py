import hashlib
import secrets
from datetime import datetime, timedelta, timezone


TOKEN_BYTES = 24


def generate_plain_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry(hours: int) -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(hours=hours)
