import re

_WORD_NUMBERS: dict[str, float] = {
    "ek": 1,
    "one": 1,
    "do": 2,
    "two": 2,
    "teen": 3,
    "three": 3,
    "char": 4,
    "chaar": 4,
    "four": 4,
    "paanch": 5,
    "panch": 5,
    "five": 5,
    "chhe": 6,
    "che": 6,
    "six": 6,
    "saat": 7,
    "seven": 7,
    "aath": 8,
    "eight": 8,
    "nau": 9,
    "nine": 9,
    "das": 10,
    "ten": 10,
    "gyarah": 11,
    "barah": 12,
    "pandrah": 15,
    "solah": 16,
    "bees": 20,
    "twenty": 20,
    "pachees": 25,
    "tees": 30,
    "chalis": 40,
    "pachas": 50,
    "saath": 60,
    "sattar": 70,
    "assi": 80,
    "nabbe": 90,
    "sau": 100,
    "hazaar": 1000,
    "hazar": 1000,
    "pav": 0.25,
    "pao": 0.25,
    "aadha": 0.5,
    "adha": 0.5,
    "half": 0.5,
    "dedh": 1.5,
    "dhai": 2.5,
}


def parse_indian_number(text: str) -> float | None:
    if not text:
        return None
    lower = text.lower().strip()

    # Check "X darjan" (dozens)
    darjan_m = re.search(r"(\d+(?:\.\d+)?|\b[a-z]+\b)\s*darjan", lower)
    if darjan_m:
        raw_mult = darjan_m.group(1)
        mult = float(raw_mult) if raw_mult.replace(".", "", 1).isdigit() else _WORD_NUMBERS.get(raw_mult, 1.0)
        return mult * 12.0

    # Check compound "do sau", "paanch sau", "do hazaar"
    comp_m = re.search(r"\b([a-z]+|\d+)\s+(sau|hazaar|hazar)\b", lower)
    if comp_m:
        head, unit_w = comp_m.group(1), comp_m.group(2)
        base_val = float(head) if head.isdigit() else _WORD_NUMBERS.get(head)
        if base_val is not None:
            return base_val * (100.0 if unit_w == "sau" else 1000.0)

    num_m = re.search(r"(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)", lower)
    if num_m:
        return float(num_m.group(1))

    for word, val in _WORD_NUMBERS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return val

    return None


def extract_post_negation_number(text: str) -> float | None:
    """
    Handles Hinglish/English corrections in both word orders:
    - Negated first: '20 pepsi nahi 10 hi biki' / 'do nahi, bas ek hi' -> 10 / 1
    - Negated last:  '2 damaged the, ek nahi' / '2 damaged, not 1' -> 2
    - Context lot + correction: 'jo 14 aaye the, unme se 2 damaged the, ek nahi' -> 2
    """
    lower = text.lower()
    num_tok = r"(?:\d+(?:\.\d+)?|" + "|".join(sorted(_WORD_NUMBERS.keys(), key=len, reverse=True)) + r")"
    cleaned = re.sub(rf"\bnot\s+{num_tok}\b", " ", lower)
    parts = re.split(r"\b(?:nahi|nahin|ki\s+jagah|instead\s+of|balki)\b", cleaned)
    if len(parts) > 1:
        after_neg = parts[-1].strip(" ,.!?")
        if after_neg:
            val = parse_indian_number(after_neg)
            if val is not None:
                return val
        without_negated = re.sub(rf"\b{num_tok}\s*(?:hi\s+)?(?:nahi|nahin)\b", " ", cleaned)
        lot_m = re.search(r"\b(?:unme|unmein|usme|usmein|inme|inmein|isme|ismein)\s+(?:se\s+)?(.+)$", without_negated)
        if lot_m:
            val = parse_indian_number(lot_m.group(1))
            if val is not None:
                return val
        val = parse_indian_number(without_negated)
        if val is not None:
            return val
    elif cleaned != lower:
        lot_m = re.search(r"\b(?:unme|unmein|usme|usmein|inme|inmein|isme|ismein)\s+(?:se\s+)?(.+)$", cleaned)
        if lot_m:
            val = parse_indian_number(lot_m.group(1))
            if val is not None:
                return val
        val = parse_indian_number(cleaned)
        if val is not None:
            return val
    return parse_indian_number(text)


def extract_post_negation_quantity(text: str) -> float | None:
    """
    Like extract_post_negation_number, but ignores size specs ('70g', '250 gram', '500ml')
    so variant corrections like '70g nahi 250 gram' never set sale quantity = 250.
    """
    cleaned = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:g|gm|gms|grams?|ml|mls|ltr|litres?|liters?)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b\d+(?:\.\d+)?(?:g|gm|ml|l)\b", " ", cleaned, flags=re.IGNORECASE)
    if not cleaned.strip():
        return None
    return extract_post_negation_number(cleaned)
