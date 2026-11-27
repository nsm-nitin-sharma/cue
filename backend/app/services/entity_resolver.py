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


_PACKAGING_STOPWORDS = frozenset(
    {
        "packet",
        "packets",
        "pkt",
        "pkts",
        "bottle",
        "bottles",
        "piece",
        "pieces",
        "pcs",
        "pc",
        "kg",
        "kilo",
        "gram",
        "grams",
        "gm",
        "g",
        "ml",
        "litre",
        "liter",
        "litres",
        "liters",
        "l",
        "box",
        "boxes",
        "pack",
        "pouch",
        "jar",
        "unit",
        "units",
        "per",
        "new",
        "product",
    }
)


def normalize_text(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s\-]", " ", raw.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_units(norm: str) -> str:
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:grams?|gms?)\b", r"\1g", norm)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:kilograms?|kilos?|kgs?)\b", r"\1kg", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:millilitres?|milliliters?|mls?)\b", r"\1ml", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s*(?:litres?|liters?)\b", r"\1l", s)
    return s


def _strip_packaging(norm: str) -> str:
    tokens = [
        tok
        for tok in norm.split()
        if tok not in _PACKAGING_STOPWORDS and not re.fullmatch(r"\d+(?:\.\d+)?(?:g|gm|kg|ml|l)?", tok)
    ]
    return " ".join(tokens).strip() or norm


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

    # 3. Token / variant containment (e.g., "pepsi" or "coke" matching multiple variants)
    core_q = _strip_packaging(_normalize_units(norm_q))
    hinted_q = " ".join(_SYNONYM_HINTS.get(tok, tok) for tok in core_q.split())
    q_tokens = {tok for tok in core_q.split() if len(tok) >= 4}
    h_tokens = {tok for tok in hinted_q.split() if len(tok) >= 4}
    variant_matches: list[dict[str, Any]] = []
    for p in products:
        p_norm = _normalize_units(normalize_text(p["name"]))
        core_p = _strip_packaging(p_norm)
        if (
            core_q in core_p
            or hinted_q in core_p
            or any(tok in core_p.split() for tok in (q_tokens | h_tokens))
        ):
            variant_matches.append(p)

    if len(variant_matches) == 1 and hinted_q == core_q:
        return ProductResolution(
            status="exact",
            product=variant_matches[0],
            spoken_term=query,
        )

    if len(variant_matches) > 1:
        return ProductResolution(
            status="ambiguous",
            candidates=variant_matches[:5],
            spoken_term=query,
        )

    # 4. Single fuzzy / phonetic match -> auto-resolve if ultra-high confidence (>= 88, e.g. "maggie masala" -> "Maggi Masala 70g"),
    #    otherwise ask "Do you mean ...?" (e.g. "coke" -> "Coca-Cola 750ml")
    hinted_q = " ".join(_SYNONYM_HINTS.get(tok, tok) for tok in core_q.split())
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in products:
        core_p = _strip_packaging(normalize_text(p["name"]))
        s1 = fuzz.WRatio(core_q, core_p)
        s2 = fuzz.WRatio(hinted_q, core_p)
        best = max(s1, s2)
        threshold = 68 if hinted_q != core_q else 74
        if best >= threshold:
            scored.append((best, p))

    for al in aliases:
        core_al = _strip_packaging(normalize_text(al["alias_text"]))
        s = max(fuzz.WRatio(core_q, core_al), fuzz.WRatio(hinted_q, core_al))
        if s >= 78:
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
        if scored[0][0] >= 88 and hinted_q == core_q:
            return ProductResolution(
                status="exact",
                product=scored[0][1],
                spoken_term=query,
            )
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
    Merges short or full-name clarification replies like '500ml', '2l', 'chhoti', or 'Maggi masala 70 gram'
    into held candidate list.
    """
    norm_u = _normalize_units(normalize_text(reply_text))
    norm = norm_u.replace(" ", "")
    if not norm:
        return None

    size_tokens = re.findall(r"\b\d+(?:\.\d+)?(?:g|kg|ml|l)\b", norm_u)
    if size_tokens:
        for c in candidates:
            c_u = _normalize_units(normalize_text(c["name"]))
            if all(st in c_u.replace(" ", "") for st in size_tokens):
                return c

    for c in candidates:
        c_u = _normalize_units(normalize_text(c["name"]))
        c_norm = c_u.replace(" ", "")
        if norm in c_norm or c_norm in norm or fuzz.partial_ratio(norm_u, c_u) >= 84:
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
