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


def _extract_size_tokens(norm_u: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:\.\d+)?(?:g|kg|ml|l)\b", norm_u))


def _sizes_conflict(q_sizes: set[str], p_norm_u: str) -> bool:
    if not q_sizes:
        return False
    p_sizes = _extract_size_tokens(p_norm_u)
    return bool(p_sizes and not (q_sizes & p_sizes))


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


def _tokens_match_product(q_tokens: list[str], p_tokens: list[str]) -> bool:
    """True if every meaningful query token matches some product word (exact or close spelling like 'maggie'->'maggi')."""
    meaningful = [t for t in q_tokens if len(t) >= 3]
    if not meaningful or not p_tokens:
        return False
    for qt in meaningful:
        ht = _SYNONYM_HINTS.get(qt, qt)
        matched = any(
            qt == pt
            or ht == pt
            or qt in pt
            or ht in pt
            or (len(qt) >= 4 and len(pt) >= 4 and fuzz.ratio(qt, pt) >= 72)
            for pt in p_tokens
        )
        if not matched:
            return False
    return True


def resolve_product(
    query: str | None,
    products: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
) -> ProductResolution:
    """
    Strict Zero-Guessing Entity Resolver:
    1. Exact normalized product name (or unit-normalized exact name like '250g' == '250 gram') -> 'exact'
    2. Multiple matching variants without disambiguating size -> 'ambiguous' (checked BEFORE aliases so adding a 2nd variant restores selection!)
    3. Exact verified alias match (only when query isn't ambiguous across multiple SKUs) -> 'exact'
    4. Single token match or fuzzy/phonetic match -> 'exact' (if high confidence) or 'verify_alias' ("Do you mean ...?")
    5. No match -> 'not_found' (triggers New Product Pop-up + voice prompt)
    """
    if not query or not query.strip():
        return ProductResolution(status="not_found", spoken_term="")

    norm_q = normalize_text(query)
    if not norm_q:
        return ProductResolution(status="not_found", spoken_term=query)

    norm_u = _normalize_units(norm_q)
    prod_by_id = {str(p["id"]): p for p in products}

    # 1. Exact product name match (raw normalized or unit-normalized e.g. 'maggi masala 250g' == 'Maggi Masala 250 Gram')
    for p in products:
        p_norm = normalize_text(p["name"])
        if p_norm == norm_q or _normalize_units(p_norm) == norm_u:
            return ProductResolution(status="exact", product=p, spoken_term=query)

    # 2. Check multi-variant containment FIRST so adding a 2nd SKU ('Maggi Masala 250 Gram') always disambiguates
    q_sizes = _extract_size_tokens(norm_u)
    core_q = _strip_packaging(norm_u)
    hinted_q = " ".join(_SYNONYM_HINTS.get(tok, tok) for tok in core_q.split())
    core_q_words = core_q.split()
    hinted_q_words = hinted_q.split()

    variant_matches: list[dict[str, Any]] = []
    for p in products:
        p_norm = _normalize_units(normalize_text(p["name"]))
        if _sizes_conflict(q_sizes, p_norm):
            continue
        core_p = _strip_packaging(p_norm)
        core_p_words = core_p.split()
        if (
            core_q in core_p
            or hinted_q in core_p
            or _tokens_match_product(core_q_words, core_p_words)
            or _tokens_match_product(hinted_q_words, core_p_words)
        ):
            variant_matches.append(p)

    if len(variant_matches) > 1:
        return ProductResolution(
            status="ambiguous",
            candidates=variant_matches[:5],
            spoken_term=query,
        )

    # 3. Exact verified alias match (only if not ambiguous across multiple SKUs)
    for al in aliases:
        al_norm = normalize_text(al["alias_text"])
        if al.get("is_verified", True) and (al_norm == norm_q or _normalize_units(al_norm) == norm_u):
            target = prod_by_id.get(str(al["product_id"]))
            if target:
                return ProductResolution(status="exact", product=target, spoken_term=query)

    if len(variant_matches) == 1 and hinted_q == core_q:
        # Guard against typos like "maggie masala" when exact spelling matched weakly via fuzzy token:
        # if core_q is verbatim in core_p, exact; if only fuzzy token matched (typo), auto-resolve if strong WRatio >= 86
        only_p = variant_matches[0]
        only_core_p = _strip_packaging(_normalize_units(normalize_text(only_p["name"])))
        if core_q in only_core_p or fuzz.WRatio(core_q, only_core_p) >= 86:
            return ProductResolution(
                status="exact",
                product=only_p,
                spoken_term=query,
            )

    # 4. Single fuzzy / phonetic match -> auto-resolve if ultra-high confidence (>= 88, e.g. "maggie masala" -> "Maggi Masala 70g"),
    #    otherwise ask "Do you mean ...?" (e.g. "coke" -> "Coca-Cola 750ml")
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in products:
        p_norm = _normalize_units(normalize_text(p["name"]))
        if _sizes_conflict(q_sizes, p_norm):
            continue
        core_p = _strip_packaging(p_norm)
        s1 = fuzz.WRatio(core_q, core_p)
        s2 = fuzz.WRatio(hinted_q, core_p)
        best = max(s1, s2)
        threshold = 68 if hinted_q != core_q else 74
        if best >= threshold:
            scored.append((best, p))

    for al in aliases:
        core_al = _strip_packaging(_normalize_units(normalize_text(al["alias_text"])))
        s = max(fuzz.WRatio(core_q, core_al), fuzz.WRatio(hinted_q, core_al))
        if s >= 78:
            target = prod_by_id.get(str(al["product_id"]))
            if target:
                t_norm = _normalize_units(normalize_text(target["name"]))
                if _sizes_conflict(q_sizes, t_norm):
                    continue
                if not any(str(x[1]["id"]) == str(target["id"]) for x in scored):
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

    # If explicit size didn't match any SKU, check if base product name matches existing variants
    # so Cue asks clarification ("Kya inmein se koi?") instead of assuming a brand-new unrelated product.
    if q_sizes:
        size_alt_matches: list[dict[str, Any]] = []
        for p in products:
            core_p = _strip_packaging(_normalize_units(normalize_text(p["name"])))
            p_words = core_p.split()
            if (
                _tokens_match_product(core_q_words, p_words)
                or _tokens_match_product(hinted_q_words, p_words)
                or fuzz.WRatio(core_q, core_p) >= 80
            ):
                size_alt_matches.append(p)
        if size_alt_matches:
            return ProductResolution(
                status="not_found",
                candidates=size_alt_matches[:4],
                spoken_term=query,
            )

    return ProductResolution(status="not_found", spoken_term=query)


def resolve_product_guarded(
    query: str | None,
    raw_transcript: str,
    products: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
) -> ProductResolution:
    """
    Runs resolve_product and guards against LLM over-normalization:
    if LLM injected a variant size token (e.g., '70g') that the user never spoke in raw_transcript,
    re-resolve without the hallucinated size so multi-variant SKUs still trigger disambiguation.
    """
    pres = resolve_product(query, products, aliases)
    if pres.status == "exact" and pres.product and query:
        p_norm = _normalize_units(normalize_text(pres.product["name"]))
        p_sizes = _extract_size_tokens(p_norm)
        t_norm = _normalize_units(normalize_text(raw_transcript))
        t_sizes = _extract_size_tokens(t_norm)
        if p_sizes and not (p_sizes & t_sizes):
            t_words = set(t_norm.split())
            size_nums = {m for tok in p_sizes for m in re.findall(r"\d+(?:\.\d+)?", tok)}
            if not (size_nums & t_words):
                stripped_q = re.sub(
                    r"\b\d+(?:\.\d+)?\s*(?:g|gm|gms|grams?|kg|kgs|kilos?|ml|mls|l|ltr|litres?|liters?)\b",
                    "",
                    query,
                    flags=re.IGNORECASE,
                ).strip()
                if stripped_q and stripped_q.lower() != query.lower():
                    alt = resolve_product(stripped_q, products, aliases)
                    if alt.status == "ambiguous":
                        return alt
    return pres


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
