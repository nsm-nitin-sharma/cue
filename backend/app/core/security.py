from collections import defaultdict, deque
import hashlib
import json
import time
from typing import Any
import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError, AuthenticationError

_ALLOWED_AUDIO_MIME_PREFIXES = (
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "video/webm",
)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    settings = get_settings()
    if not settings.SUPABASE_URL:
        return None
    if _jwks_client is None:
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_audio_upload(data: bytes, content_type: str | None) -> None:
    settings = get_settings()
    if not data or len(data) < 400:
        raise AudioValidationError("Recording was empty or too short. Please speak clearly and try again.")
    if len(data) > settings.max_audio_bytes:
        raise AudioValidationError(
            f"Audio exceeds maximum allowed size of {settings.MAX_AUDIO_UPLOAD_MB} MB."
        )

    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct and not any(ct.startswith(prefix) for prefix in _ALLOWED_AUDIO_MIME_PREFIXES):
            raise AudioValidationError(f"Unsupported audio format: {ct}")

    # Magic-byte verification for common audio containers
    header = data[:16]
    is_webm = header.startswith(b"\x1a\x45\xdf\xa3")
    is_ogg = header.startswith(b"OggS")
    is_wav = header.startswith(b"RIFF") and data[8:12] == b"WAVE"
    is_mp4 = len(header) >= 8 and header[4:8] == b"ftyp"
    is_mp3 = header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)
    if not (is_webm or is_ogg or is_wav or is_mp4 or is_mp3):
        raise AudioValidationError("Audio file signature failed validation.")


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True


rate_limiter = SlidingWindowRateLimiter(
    max_requests=get_settings().RATE_LIMIT_REQUESTS_PER_MINUTE,
    window_seconds=60,
)


async def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Verify Supabase user JWT via JWKS (ECC/RS256) with fallback to Supabase /auth/v1/user.
    Returns dict containing verified `user_id` and `email`.
    """
    if not token or len(token) < 20:
        raise AuthenticationError("Missing bearer token")

    settings = get_settings()
    jwks_client = _get_jwks_client()
    if jwks_client is not None:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
            )
            sub = claims.get("sub")
            if sub:
                return {"user_id": str(sub), "email": claims.get("email", "")}
        except jwt.PyJWTError:
            pass

    # Fallback: direct Supabase Auth introspection (supports HS256 & newly rotated keys)
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise AuthenticationError("Supabase auth configuration missing")

    auth_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                auth_url,
                headers={
                    "apikey": settings.SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {token}",
                },
            )
        if resp.status_code != 200:
            raise AuthenticationError("Invalid or expired session token")
        user_data = resp.json()
        uid = user_data.get("id")
        if not uid:
            raise AuthenticationError("Token missing user subject")
        return {"user_id": str(uid), "email": user_data.get("email", "")}
    except httpx.HTTPError as exc:
        raise AuthenticationError("Authentication verification unreachable") from exc
