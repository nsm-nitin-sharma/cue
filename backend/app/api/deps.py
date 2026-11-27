from typing import Any
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError
from app.core.security import rate_limiter, verify_supabase_jwt
from app.db.supabase_client import get_admin_supabase

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if not creds or not creds.credentials:
        raise AuthenticationError("Authorization bearer token required")
    user = await verify_supabase_jwt(creds.credentials)
    if not rate_limiter.check(f"user:{user['user_id']}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a moment.")
    return user


def get_active_business_id(
    user: dict[str, Any] = Depends(get_current_user),
    x_business_id: str | None = Header(default=None),
) -> str:
    """
    Resolve active tenant strictly from verified `business_members` table.
    Never trusts arbitrary client-supplied business IDs without DB membership proof.
    """
    db = get_admin_supabase()
    query = (
        db.table("business_members")
        .select("business_id, role")
        .eq("user_id", user["user_id"])
        .eq("is_active", True)
    )
    if x_business_id:
        query = query.eq("business_id", x_business_id)
    res = query.limit(1).execute()
    if not res.data:
        raise HTTPException(
            status_code=404,
            detail="No active store found for this account. Complete onboarding first.",
        )
    return str(res.data[0]["business_id"])
