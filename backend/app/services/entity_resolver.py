from dataclasses import dataclass
import re
from typing import Any, Literal
from rapidfuzz import fuzz

_SYNONYM_HINTS: dict[str, str] = {
    "coke": "coca-cola",
    "thanda": "pepsi",
    "chotti": "chhoti",
    "baddi": "badi",
    "namak": "salt",
    "tel": "oil",
    "doodh": "milk",
}


def normalize_text(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", raw.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


@dataclass
class ProductResolution:
    status: Literal["exact", "verify_alias", "ambiguous", "not_found"]
    product: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] | None = None
    spoken_term: str = ""


@dataclass
class CustomerResolution:
    status: Literal["exact", "ambiguous", "not_found"]
    customer: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] | None = None
    spoken_term: str = ""


def resolve_product(
    query: str | None,
    products: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
) -> ProductResolution:
    """
    Strict Zero-Guessing Entity Resolver:
    1. Exact normalized product name or verified alias -> 'exact'
    2. Multiple strong matches (e.g. 'pepsi' -> 500ml & 2L) -> 'ambiguous'
    3. Single fuzzy/phonetic match without verified alias (e.g. 'coke' -> Coca-Cola) -> 'verify_alias' ("Do you mean ...?")
    4. No match -> 'not_found' (triggers New Product Pop-up + voice prompt)
    """
    if not query or not query.strip():
        return ProductResolution(status="not_found", spoken_term="")

    norm_q = normalize_text(query)
    if not norm_q:
        return ProductResolution(status="not_found", spoken_term=query)

    prod_by_id = {str(p["id"]): p for p in products}

    # 1. Exact product name match
    for p in products:
        if normalize_text(p["name"]) == norm_q:
            return ProductResolution(status="exact", product=p, spoken_term=query)

    # 2. Exact verified alias match
    for al in aliases:
        if al.get("is_verified", True) and normalize_text(al["alias_text"]) == norm_q:
            target = prod_by_id.get(str(al["product_id"]))
            if target:
                return ProductResolution(status="exact", product=target, spoken_term=query)

    # 3. Token / variant containment (e.g., "pepsi" matching multiple variants)
    q_tokens = set(norm_q.split())
    variant_matches: list[dict[str, Any]] = []
    for p in products:
        p_norm = normalize_text(p["name"])
        if norm_q in p_norm or any(tok in p_norm.split() for tok in q_tokens if len(tok) >= 4):
            variant_matches.append(p)

    if len(variant_matches) > 1:
        return ProductResolution(
            status="ambiguous",
            candidates=variant_matches[:5],
            spoken_term=query,
        )

    # 4. Single fuzzy / phonetic match -> ALWAYS ask "Do you mean ...?" instead of guessing
    hinted_q = " ".join(_SYNONYM_HINTS.get(tok, tok) for tok in norm_q.split())
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in products:
        p_norm = normalize_text(p["name"])
        s1 = fuzz.WRatio(norm_q, p_norm)
        s2 = fuzz.WRatio(hinted_q, p_norm)
        best = max(s1, s2)
        if best >= 68:
            scored.append((best, p))

    for al in aliases:
        al_norm = normalize_text(al["alias_text"])
        s = max(fuzz.WRatio(norm_q, al_norm), fuzz.WRatio(hinted_q, al_norm))
        if s >= 76:
            target = prod_by_id.get(str(al["product_id"]))
            if target and not any(str(x[1]["id"]) == str(target["id"]) for x in scored):
                scored.append((s, target))

    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < 12:
        return ProductResolution(
            status="ambiguous",
            candidates=[item[1] for item in scored[:4]],
            spoken_term=query,
        )
    if len(scored) >= 1:
        return ProductResolution(
            status="verify_alias",
            product=scored[0][1],
            candidates=[scored[0][1]],
            spoken_term=query,
        )

    return ProductResolution(status="not_found", spoken_term=query)


def resolve_short_variant_reply(
    reply_text: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Merges short clarification replies like '500ml', '2l', 'chhoti' into held candidate list.
    """
    norm = normalize_text(reply_text).replace(" ", "")
    if not norm:
        return None

    for c in candidates:
        c_norm = normalize_text(c["name"]).replace(" ", "")
        if norm in c_norm or fuzz.partial_ratio(normalize_text(reply_text), normalize_text(c["name"])) >= 82:
            return c
        if any(w in norm for w in ("chhoti", "chotti", "small")) and "500" in c_norm:
            return c
        if any(w in norm for w in ("badi", "baddi", "large")) and ("2l" in c_norm or "1l" in c_norm):
            return c
    return None


def resolve_customer(
    query: str | None,
    customers: list[dict[str, Any]],
) -> CustomerResolution:
    if not query or not query.strip():
        return CustomerResolution(status="not_found", spoken_term="")

    norm_q = normalize_text(query)
    exact = [c for c in customers if normalize_text(c["name"]) == norm_q]
    if len(exact) == 1:
        return CustomerResolution(status="exact", customer=exact[0], spoken_term=query)

    partial = [
        c
        for c in customers
        if norm_q in normalize_text(c["name"])
        or normalize_text(c["name"]) in norm_q
        or fuzz.WRatio(norm_q, normalize_text(c["name"])) >= 75
    ]
    if len(partial) == 1:
        return CustomerResolution(status="exact", customer=partial[0], spoken_term=query)
    if len(partial) > 1:
        return CustomerResolution(status="ambiguous", candidates=partial[:5], spoken_term=query)

    return CustomerResolution(status="not_found", spoken_term=query)
