from dataclasses import dataclass
from functools import lru_cache
from typing import Any
import httpx

from app.core.config import get_settings


@dataclass
class RestResponse:
    data: Any


class _TableQueryBuilder:
    def __init__(self, client: httpx.Client, base_url: str, headers: dict[str, str], table: str):
        self._client = client
        self._url = f"{base_url}/rest/v1/{table}"
        self._headers = dict(headers)
        self._method = "GET"
        self._params: list[tuple[str, str]] = []
        self._json_body: Any = None

    def select(self, columns: str = "*") -> "_TableQueryBuilder":
        self._method = "GET"
        self._params.append(("select", columns))
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "_TableQueryBuilder":
        self._method = "POST"
        self._json_body = payload
        self._headers["Prefer"] = "return=representation"
        return self

    def upsert(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str | None = None,
    ) -> "_TableQueryBuilder":
        self._method = "POST"
        self._json_body = payload
        self._headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        if on_conflict:
            self._params.append(("on_conflict", on_conflict))
        return self

    def update(self, payload: dict[str, Any]) -> "_TableQueryBuilder":
        self._method = "PATCH"
        self._json_body = payload
        self._headers["Prefer"] = "return=representation"
        return self

    def eq(self, col: str, val: Any) -> "_TableQueryBuilder":
        v = "true" if val is True else ("false" if val is False else str(val))
        self._params.append((col, f"eq.{v}"))
        return self

    def neq(self, col: str, val: Any) -> "_TableQueryBuilder":
        self._params.append((col, f"neq.{val}"))
        return self

    def gt(self, col: str, val: Any) -> "_TableQueryBuilder":
        self._params.append((col, f"gt.{val}"))
        return self

    def gte(self, col: str, val: Any) -> "_TableQueryBuilder":
        self._params.append((col, f"gte.{val}"))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_TableQueryBuilder":
        joined = ",".join(str(v) for v in vals)
        self._params.append((col, f"in.({joined})"))
        return self

    def order(self, col: str, desc: bool = False) -> "_TableQueryBuilder":
        self._params.append(("order", f"{col}.{'desc' if desc else 'asc'}"))
        return self

    def limit(self, count: int) -> "_TableQueryBuilder":
        self._params.append(("limit", str(count)))
        return self

    def execute(self) -> RestResponse:
        resp = self._client.request(
            self._method,
            self._url,
            params=self._params,
            json=self._json_body,
            headers=self._headers,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase REST error ({resp.status_code}): {resp.text}")
        if not resp.text:
            return RestResponse(data=[])
        return RestResponse(data=resp.json())


class _RpcQueryBuilder:
    def __init__(self, client: httpx.Client, base_url: str, headers: dict[str, str], fn_name: str, params: dict[str, Any]):
        self._client = client
        self._url = f"{base_url}/rest/v1/rpc/{fn_name}"
        self._headers = dict(headers)
        self._params = params

    def execute(self) -> RestResponse:
        resp = self._client.post(self._url, json=self._params, headers=self._headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase RPC error ({resp.status_code}): {resp.text}")
        if not resp.text:
            return RestResponse(data=None)
        return RestResponse(data=resp.json())


class SupabaseRestClient:
    """
    Lightweight PostgREST + RPC client supporting BOTH legacy JWT keys (eyJ...)
    and Supabase's modern `sb_secret_...` keys cleanly.
    """

    def __init__(self, url: str, secret_key: str):
        self._base_url = url.rstrip("/")
        self._headers: dict[str, str] = {
            "apikey": secret_key,
            "Content-Type": "application/json",
        }
        if secret_key.startswith("eyJ"):
            self._headers["Authorization"] = f"Bearer {secret_key}"
        self._client = httpx.Client(timeout=15.0)

    def table(self, name: str) -> _TableQueryBuilder:
        return _TableQueryBuilder(self._client, self._base_url, self._headers, name)

    def rpc(self, fn_name: str, params: dict[str, Any] | None = None) -> _RpcQueryBuilder:
        return _RpcQueryBuilder(self._client, self._base_url, self._headers, fn_name, params or {})


@lru_cache(maxsize=1)
def get_admin_supabase() -> SupabaseRestClient:
    """
    Server-side Supabase REST client.
    MUST ONLY be called after JWT verification and business_members authorization.
    """
    settings = get_settings()
    return SupabaseRestClient(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
