from dataclasses import dataclass
import re
from typing import Any, Literal
from rapidfuzz import fuzz

from app.domain.indian_numbers import parse_indian_number

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

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PRICE_UNIT_EXCLUSION = r"(?:g|gm|gms|grams?|kg|kgs|kilograms?|kilos?|ml|mls|l|ltr|litres?|liters?|packets?|pkts?|pieces?|pcs?|box(?:es)?|bottles?|jars?|cans?)"
_PRICE_CURRENCY_WORDS = r"(?:rs\.?|rupees?|rupaye|rupaiye|rupaiya|rupay|rupe|rupia|rupi|inr|रुपये|रुपए|रु)"
_PRICE_SELECTOR_WORDS = r"(?:wal[aei]|val[aei]|वली|वाली|वाला)"
_NON_PRODUCT_KA_FOLLOWERS = r"(?:udhaar|udhar|credit|saaman|saman|maal|bill|kharcha|kharch|expense|note|discount|loss|profit|payment|hisaab|hisab|balance)"
_WORD_NUM_ALT = (
    r"(?:ek|do|teen|chaar|char|paanch|panch|chhe|che|saat|aath|nau|das|gyarah|barah|baarah|"
    r"terah|chaudah|pandrah|solah|satrah|atharah|unnis|bees|pachees|pachis|tees|chalis|chaalis|"
    r"pachas|pachaas|sattar|assi|nabbe|sau|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)"
)


def extract_product_price_hint(text: str | None) -> tuple[str, float | None]:
    """
    Extracts an item-identifying price tag (e.g., 'Maggi 10 rupe vali', '₹12 wali', '10 rs',
    'das rupaye wali maggi', '10 ka maggi') and returns (cleaned_text, price_val).
    Deliberately ignores weight/size selectors ('250 gram wali', '2 kg') and explicit sale-price
    phrases ('15 rupaye mein bechi').
    """
    if not text or not text.strip():
        return ("", None)

    working = text.translate(_DEVANAGARI_DIGITS).strip()
    patterns: list[tuple[re.Pattern[str], bool]] = [
        # ₹10 / ₹ 10 wali / Rs. 10 / INR 12
        (
            re.compile(
                rf"(?:₹\s*|(?:\b(?:rs\.?|inr)\s*))(\d+(?:\.\d+)?)\s*(?:{_PRICE_CURRENCY_WORDS}?\s*{_PRICE_SELECTOR_WORDS}?|(?:ka|ki|ke)(?!\s+{_NON_PRODUCT_KA_FOLLOWERS})\b)?",
                re.IGNORECASE,
            ),
            False,
        ),
        # 10 rupaye wali / 10 rupe vali / 10 rs / 10/- rs (NOT '10 rupaye mein')
        (
            re.compile(
                rf"\b(\d+(?:\.\d+)?)\s*(?:/-\s*)?{_PRICE_CURRENCY_WORDS}(?!\s*(?:mein|me|main)\b)(?:\s+{_PRICE_SELECTOR_WORDS}|\s+(?:ka|ki|ke)(?!\s+{_NON_PRODUCT_KA_FOLLOWERS}))?(?=\s|$|[.,!?])",
                re.IGNORECASE,
            ),
            False,
        ),
        # 10 wali / 12 vali / 33 wala (no unit word like gram/ml before wali)
        (
            re.compile(
                rf"\b(\d+(?:\.\d+)?)\s*{_PRICE_SELECTOR_WORDS}(?=\s|$|[.,!?])",
                re.IGNORECASE,
            ),
            False,
        ),
        # 10 ka maggi / 10 ki coke (exclude udhaar/saaman/weight units)
        (
            re.compile(
                rf"\b(\d+(?:\.\d+)?)\s+(?:ka|ki)(?!\s+(?:{_NON_PRODUCT_KA_FOLLOWERS}|{_PRICE_UNIT_EXCLUSION}|%|percent))(?=\s+[a-z\u0900-\u097F]|\s*$|[.,!?])",
                re.IGNORECASE,
            ),
            False,
        ),
        # Word numbers: das rupaye wali / bees wali / pachas rs
        (
            re.compile(
                rf"\b((?:{_WORD_NUM_ALT}\s+)?{_WORD_NUM_ALT})\s+(?:{_PRICE_CURRENCY_WORDS}(?!\s*(?:mein|me|main)\b)(?:\s+{_PRICE_SELECTOR_WORDS})?|{_PRICE_SELECTOR_WORDS})(?=\s|$|[.,!?])",
                re.IGNORECASE,
            ),
            True,
        ),
    ]

    for pat, is_word in patterns:
        m = pat.search(working)
        if not m:
            continue
        raw_val = m.group(1)
        val = parse_indian_number(raw_val) if is_word else float(raw_val)
        if val is None or val <= 0:
            continue
        before = working[: m.start()].strip()
        after = working[m.end() :].strip()
        # Strip lingering connector 'ka'/'ki'/'ke'/'of' ONLY when adjacent to the removed price span
        if re.search(r"\b(?:of|for)$", before, re.IGNORECASE):
            before = re.sub(r"\s*\b(?:of|for)$", "", before, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", f"{before} {after}").strip(" ,.-")
        return (cleaned, float(val))

    return (working, None)


def extract_clause_price_hint(query: str | None, raw_transcript: str) -> float | None:
    """
    When LLM omitted price_hint on an operation, recover an explicit price qualifier from the
    relevant clause of raw_transcript (without leaking prices between multi-item clauses).
    """
    if not raw_transcript or not raw_transcript.strip():
        return None
    clauses = [c.strip() for c in re.split(r"(?:,|\baur\b|\band\b)", raw_transcript, flags=re.IGNORECASE) if c.strip()]
    if not clauses:
        clauses = [raw_transcript]

    q_tokens = [t for t in normalize_text(query or "").split() if len(t) >= 3]
    target_clause: str | None = None
    if len(clauses) == 1:
        target_clause = clauses[0]
    elif q_tokens:
        for cl in clauses:
            cl_norm = normalize_text(cl)
            if any(qt in cl_norm or fuzz.partial_ratio(qt, cl_norm) >= 82 for qt in q_tokens):
                target_clause = cl
                break
    if not target_clause:
        return None
    _, val = extract_product_price_hint(target_clause)
    return val


def _product_matches_price(product: dict[str, Any], price_hint: float) -> bool:
    sp = product.get("default_selling_price")
    if sp is None:
        return False
    try:
        sp_val = float(sp)
    except (TypeError, ValueError):
        return False
    if sp_val <= 0 and price_hint > 0:
        return False
    return abs(sp_val - price_hint) <= 0.01


def filter_candidates_by_price(candidates: list[dict[str, Any]], price_hint: float) -> list[dict[str, Any]]:
    return [c for c in candidates if _product_matches_price(c, price_hint)]


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
    price_hint: float | None = None,
) -> ProductResolution:
    """
    Strict Zero-Guessing Entity Resolver:
    1. Exact normalized product name (or unit-normalized exact name like '250g' == '250 gram') -> 'exact'
    2. Multiple matching variants without disambiguating size -> narrowed by price_hint if spoken;
       if 1 variant matches price -> 'exact', if >=2 share the same price -> 'ambiguous' (asks confirmation!)
    3. Exact verified alias match (only when query isn't ambiguous across multiple SKUs) -> 'exact'
    4. Single token match or fuzzy/phonetic match -> 'exact' (if high confidence) or 'verify_alias' ("Do you mean ...?")
    5. No match -> 'not_found' (triggers New Product Pop-up + voice prompt)
    """
    if not query or not query.strip():
        return ProductResolution(status="not_found", spoken_term="")

    raw_norm_q = normalize_text(query)
    if not raw_norm_q:
        return ProductResolution(status="not_found", spoken_term=query)

    raw_norm_u = _normalize_units(raw_norm_q)
    prod_by_id = {str(p["id"]): p for p in products}

    # 1. Exact product name match (raw normalized or unit-normalized e.g. 'maggi masala 250g' == 'Maggi Masala 250 Gram')
    for p in products:
        p_norm = normalize_text(p["name"])
        if p_norm == raw_norm_q or _normalize_units(p_norm) == raw_norm_u:
            if price_hint is None or _product_matches_price(p, float(price_hint)) or float(p.get("default_selling_price") or 0) <= 0:
                return ProductResolution(status="exact", product=p, spoken_term=query)

    # Extract embedded price-selector qualifier (e.g. 'maggie 10 rupe vali' -> clean_q='maggie', eff_price=10)
    clean_q, parsed_price = extract_product_price_hint(query)
    eff_price: float | None = float(price_hint) if price_hint is not None else parsed_price

    if eff_price is not None and not clean_q.strip():
        priced_all = filter_candidates_by_price(products, eff_price)
        if len(priced_all) == 1:
            return ProductResolution(status="exact", product=priced_all[0], spoken_term=query)
        if len(priced_all) > 1:
            return ProductResolution(status="ambiguous", candidates=priced_all[:5], spoken_term=query)
        return ProductResolution(status="not_found", spoken_term=query)

    norm_q = normalize_text(clean_q or query)
    if not norm_q:
        return ProductResolution(status="not_found", spoken_term=query)
    norm_u = _normalize_units(norm_q)

    # Exact product name match after stripping price tag (e.g. 'Maggi Masala 70g 12 rupaye wali')
    if clean_q and norm_q != raw_norm_q:
        for p in products:
            p_norm = normalize_text(p["name"])
            if p_norm == norm_q or _normalize_units(p_norm) == norm_u:
                if eff_price is None or _product_matches_price(p, eff_price) or float(p.get("default_selling_price") or 0) <= 0:
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
        if eff_price is not None:
            priced = filter_candidates_by_price(variant_matches, eff_price)
            if len(priced) == 1:
                return ProductResolution(status="exact", product=priced[0], spoken_term=query)
            if len(priced) > 1:
                return ProductResolution(status="ambiguous", candidates=priced[:5], spoken_term=query)
            return ProductResolution(status="not_found", candidates=variant_matches[:4], spoken_term=query)
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
                t_sp = float(target.get("default_selling_price") or 0)
                if eff_price is not None and t_sp > 0 and not _product_matches_price(target, eff_price):
                    continue
                return ProductResolution(status="exact", product=target, spoken_term=query)

    if len(variant_matches) == 1 and hinted_q == core_q:
        # Guard against typos like "maggie masala" when exact spelling matched weakly via fuzzy token:
        # if core_q is verbatim in core_p, exact; if only fuzzy token matched (typo), auto-resolve if strong WRatio >= 86
        only_p = variant_matches[0]
        only_sp = float(only_p.get("default_selling_price") or 0)
        if eff_price is not None and only_sp > 0 and not _product_matches_price(only_p, eff_price):
            return ProductResolution(status="not_found", candidates=[only_p], spoken_term=query)
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
        scored_prods = [item[1] for item in scored]
        if eff_price is not None:
            priced_scored = filter_candidates_by_price(scored_prods, eff_price)
            if len(priced_scored) == 1:
                return ProductResolution(status="exact", product=priced_scored[0], spoken_term=query)
            if len(priced_scored) > 1:
                return ProductResolution(status="ambiguous", candidates=priced_scored[:4], spoken_term=query)
            return ProductResolution(status="not_found", candidates=scored_prods[:4], spoken_term=query)
        return ProductResolution(
            status="ambiguous",
            candidates=scored_prods[:4],
            spoken_term=query,
        )
    if len(scored) >= 1:
        top_p = scored[0][1]
        top_sp = float(top_p.get("default_selling_price") or 0)
        if eff_price is not None and top_sp > 0 and not _product_matches_price(top_p, eff_price):
            return ProductResolution(status="not_found", candidates=[item[1] for item in scored[:4]], spoken_term=query)
        if (scored[0][0] >= 88 and hinted_q == core_q) or (
            eff_price is not None and _product_matches_price(top_p, eff_price)
        ):
            return ProductResolution(
                status="exact",
                product=top_p,
                spoken_term=query,
            )
        return ProductResolution(
            status="verify_alias",
            product=top_p,
            candidates=[top_p],
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
    price_hint: float | None = None,
) -> ProductResolution:
    """
    Runs resolve_product and guards against LLM over-normalization:
    - Extracts explicit price-selector hints (e.g. '10 rupe vali') from query or raw_transcript clause.
    - If LLM injected a variant size ('70g') OR sub-variant word ('Masala') that the user never spoke
      in raw_transcript, re-resolves with only spoken tokens so multi-variant / same-price SKUs still trigger disambiguation.
    """
    _, q_price = extract_product_price_hint(query)
    eff_price: float | None = (
        float(price_hint)
        if price_hint is not None
        else (q_price if q_price is not None else extract_clause_price_hint(query, raw_transcript))
    )

    pres = resolve_product(query, products, aliases, price_hint=eff_price)
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
                stripped_core = _strip_packaging(normalize_text(stripped_q))
                t_mentioned_brand = bool(
                    stripped_core
                    and any(
                        tok in t_norm or fuzz.partial_ratio(tok, t_norm) >= 82
                        for tok in stripped_core.split()
                        if len(tok) >= 3
                    )
                )
                if stripped_q and stripped_q.lower() != query.lower() and t_mentioned_brand:
                    alt = resolve_product(stripped_q, products, aliases, price_hint=eff_price)
                    if alt.status == "ambiguous":
                        return alt

        # Also guard against LLM injecting flavor/sub-variant words (e.g. 'Masala' when user only said 'maggie 10 rupe vali')
        clean_q, _ = extract_product_price_hint(query)
        clean_u = _normalize_units(normalize_text(clean_q))
        t_split = t_norm.split()
        kept_toks: list[str] = []
        dropped_word = False
        for tok in clean_u.split():
            if re.fullmatch(r"\d+(?:\.\d+)?(?:g|kg|ml|l)?", tok) or tok in _PACKAGING_STOPWORDS:
                kept_toks.append(tok)
            elif tok in t_norm or any(fuzz.ratio(tok, tw) >= 78 for tw in t_split if len(tw) >= 2):
                kept_toks.append(tok)
            else:
                dropped_word = True
        if dropped_word and any(not re.fullmatch(r"\d+(?:\.\d+)?(?:g|kg|ml|l)?", t) for t in kept_toks):
            alt2 = resolve_product(" ".join(kept_toks), products, aliases, price_hint=eff_price)
            if alt2.status == "ambiguous":
                return alt2

    return pres


def resolve_short_variant_reply(
    reply_text: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Merges short or full-name clarification replies like '500ml', '2l', 'chhoti',
    '10 rupaye wali', or 'Maggi masala 70 gram' into held candidate list.
    """
    norm_u = _normalize_units(normalize_text(reply_text))
    norm = norm_u.replace(" ", "")
    if not norm:
        return None

    # Exact / full candidate name match first (critical when multiple variants share size, e.g. '70g' Masala vs Atta)
    for c in candidates:
        c_u = _normalize_units(normalize_text(c["name"]))
        if c_u == norm_u or c_u.replace(" ", "") == norm:
            return c

    size_tokens = re.findall(r"\b\d+(?:\.\d+)?(?:g|kg|ml|l)\b", norm_u)
    if size_tokens:
        size_matched = [
            c
            for c in candidates
            if all(st in _normalize_units(normalize_text(c["name"])).replace(" ", "") for st in size_tokens)
        ]
        if len(size_matched) == 1:
            return size_matched[0]
        if len(size_matched) > 1:
            # Disambiguate among same-size candidates by flavor/sub-words if spoken (e.g., "Maggi Atta 70g")
            best_sub = next(
                (
                    c
                    for c in size_matched
                    if norm in _normalize_units(normalize_text(c["name"])).replace(" ", "")
                    or fuzz.ratio(norm_u, _normalize_units(normalize_text(c["name"]))) >= 85
                ),
                None,
            )
            if best_sub:
                return best_sub
            return size_matched[0]

    # Price-based selection (e.g. '10 rupaye wali', '₹12', or bare '33' matching MRP)
    _, reply_price = extract_product_price_hint(reply_text)
    if reply_price is None and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", reply_text.strip()):
        cand_num = float(reply_text.strip())
        num_str = str(int(cand_num)) if cand_num == int(cand_num) else str(cand_num)
        num_in_name = any(re.search(rf"\b{re.escape(num_str)}\b", str(c.get("name") or "")) for c in candidates)
        if not num_in_name and filter_candidates_by_price(candidates, cand_num):
            reply_price = cand_num

    if reply_price is not None:
        priced = filter_candidates_by_price(candidates, reply_price)
        if len(priced) == 1:
            return priced[0]
        if len(priced) > 1:
            return None

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
