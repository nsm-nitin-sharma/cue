import re
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("cue.i18n")

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Common kirana / retail Devanagari words -> exact Romanized Hinglish spelling
_WORD_MAP: dict[str, str] = {
    "मैगी": "Maggie",
    "मेगी": "Maggie",
    "मसाला": "Masala",
    "कोक": "Coke",
    "कोका": "Coca",
    "कोला": "Cola",
    "पेप्सी": "Pepsi",
    "चीनी": "Chini",
    "सर्फ": "Surf",
    "एक्सेल": "Excel",
    "नेस्कैफे": "Nescafe",
    "गोल्ड": "Gold",
    "जार": "Jar",
    "अमूल": "Amul",
    "टाटा": "Tata",
    "नमक": "Namak",
    "तेल": "Tel",
    "दूध": "Doodh",
    "ग्राम": "gram",
    "किलो": "kilo",
    "लीटर": "litre",
    "पैकेट": "packet",
    "पीस": "piece",
    "बोतल": "bottle",
    "पेटी": "peti",
    "बॉक्स": "box",
    "दर्जन": "darjan",
    "नितिन": "Nitin",
    "शर्मा": "Sharma",
    "राहुल": "Rahul",
    "रमेश": "Ramesh",
    "गुप्ता": "Gupta",
    "यादव": "Yadav",
    "सेल": "sale",
    "सीएल": "sale",
    "उधार": "udhaar",
    "खाता": "khata",
    "खाते": "khate",
    "कैश": "cash",
    "ऑनलाइन": "online",
    "यूपीआई": "UPI",
    "जीपे": "GPay",
    "फोनपे": "PhonePe",
    "पेटीएम": "Paytm",
    "इन्वेंटरी": "inventory",
    "स्टॉक": "stock",
    "बिल": "bill",
    "बिजली": "bijli",
    "खर्च": "kharch",
    "खर्चा": "kharcha",
    "पेमेंट": "payment",
    "पेंडिंग": "pending",
    "कस्टमर": "customer",
    "प्रोडक्ट": "product",
    "आइटम": "item",
    "ऑर्डर": "order",
    "लास्ट": "last",
    "ट्रांजैक्शन": "transaction",
    "ट्रांजेक्शन": "transaction",
    "आज": "aaj",
    "कल": "kal",
    "परसों": "parso",
    "कितनी": "kitni",
    "कितना": "kitna",
    "कितने": "kitne",
    "हुई": "hui",
    "हुआ": "hua",
    "हुए": "hue",
    "बिकी": "biki",
    "बिका": "bika",
    "बिके": "bike",
    "बेची": "bechi",
    "बेचा": "becha",
    "आई": "aayi",
    "आया": "aaya",
    "आए": "aaye",
    "गई": "gayi",
    "गया": "gaya",
    "गए": "gaye",
    "ली": "li",
    "लिया": "liya",
    "दी": "di",
    "दिया": "diya",
    "दिए": "diye",
    "दे": "de",
    "लिख": "likh",
    "दो": "do",
    "करो": "karo",
    "डिलीट": "delete",
    "सारा": "saara",
    "डेटा": "data",
    "नहीं": "nahi",
    "नही": "nahi",
    "हां": "haan",
    "हाँ": "haan",
    "जी": "ji",
    "नया": "naya",
    "नई": "nayi",
    "नयी": "nayi",
    "और": "aur",
    "या": "ya",
    "से": "se",
    "को": "ko",
    "में": "mein",
    "पर": "par",
    "पे": "pe",
    "की": "ki",
    "के": "ke",
    "का": "ka",
    "है": "hai",
    "हैं": "hain",
    "था": "tha",
    "थी": "thi",
    "थे": "the",
    "रुपए": "rupaye",
    "रुपये": "rupaye",
    "एक": "ek",
    "तीन": "teen",
    "चार": "chaar",
    "पांच": "paanch",
    "पाँच": "paanch",
    "छह": "chhe",
    "सात": "saat",
    "आठ": "aath",
    "नौ": "nau",
    "दस": "das",
    "बीस": "bees",
    "पचास": "pachas",
    "सौ": "sau",
    "हजार": "hazaar",
    "हज़ार": "hazaar",
    "ढाई": "dhai",
    "आधा": "aadha",
    "डेढ़": "dedh",
    "डेमिस": "damaged",
    "डैमेज": "damaged",
    "डैमेज्ड": "damaged",
    "खराब": "kharab",
    "एक्सपायर": "expired",
    "एक्सपायर्ड": "expired",
    "बस": "bas",
    "ही": "hi",
    "जो": "jo",
    "उन": "un",
    "उनमें": "unme",
    "आये": "aaye",
}

_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ं": "n", "ँ": "n", "ः": "h",
}
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f",
}
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _transliterate_token(tok: str) -> str:
    if not _DEVANAGARI_RE.search(tok):
        return tok
    core = tok.translate(_DIGITS)
    stripped = re.sub(r"^[^\w\u0900-\u097F]+|[^\w\u0900-\u097F]+$", "", core)
    if stripped in _WORD_MAP:
        return core.replace(stripped, _WORD_MAP[stripped], 1)

    out: list[str] = []
    i = 0
    n = len(core)
    while i < n:
        ch = core[i]
        # Handle nukta digraphs
        if i + 1 < n and core[i + 1] == "़" and (ch + "़") in _CONSONANTS:
            ch = ch + "़"
            i += 1
        if ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            nxt = core[i + 1] if i + 1 < n else ""
            if nxt == "्":
                i += 1  # halant suppresses inherent 'a'
            elif nxt in _MATRAS:
                pass
            elif i + 1 < n and _DEVANAGARI_RE.match(nxt):
                out.append("a")
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])
        elif ch != "्":
            out.append(ch)
        i += 1
    return "".join(out)


def romanize_devanagari_to_hinglish(text: str) -> str:
    """Convert Devanagari speech transcripts into clean Romanized Hinglish when Hinglish mode is selected."""
    if not text or not _DEVANAGARI_RE.search(text):
        return text
    # Normalize "सी एल" -> "sale" before token split
    pre = text.replace("सी एल", "sale")
    tokens = pre.split()
    converted = [_transliterate_token(t) for t in tokens]
    return re.sub(r"\s+", " ", " ".join(converted)).strip()


# Fast deterministic Hinglish -> English phrase rules (zero API latency)
_EN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^Aaj abhi tak (\d+) sales hui hain, total (₹[\d,]+) \(Collected (₹[\d,]+), Udhaar (₹[\d,]+)\)\.$"),
        r"Today's total so far: \1 sales amounting to \2 (Collected \3, Udhaar \4).",
    ),
    (
        re.compile(r"^Aaj abhi tak (.+?) ki total ([\d.]+) units \((₹[\d,]+)\) ki sale hui hai\.$"),
        r"Today's sales for \1: \2 units totaling \3.",
    ),
    (
        re.compile(r"^Aaj abhi tak (.+?) ki koi sale nahi hui hai\.$"),
        r"No sales recorded for \1 today yet.",
    ),
    (
        re.compile(r"^Inventory mein total (\d+) items hain(.*)$"),
        r"There are \1 items in inventory\2",
    ),
    (
        re.compile(r"^Inventory mein abhi ([\d.]+) (\S+) (.+?) available hain\.$"),
        r"Currently \1 \2 of \3 are available in inventory.",
    ),
    (
        re.compile(r"^Inventory mein '(.+?)' naam ka koi product nahi mila\.$"),
        r"No product named '\1' was found in inventory.",
    ),
    (
        re.compile(r"^Aapki inventory abhi khaali hai\. Naya stock bol kar add karein\.$"),
        r"Your inventory is currently empty. Speak to add new stock.",
    ),
    (
        re.compile(r"^([\d.]+) (.+?) ki (Cash|Online|Bank) sale \((₹[\d,]+)\) save ho gayi\.$"),
        r"Saved \3 sale for \1 \2 (\4).",
    ),
    (
        re.compile(r"^([\d.]+) (.+?) (.+?) ke Khata mein Udhaar \((₹[\d,]+)\) add ho gayi\. Revenue mein abhi add nahi hua\.$"),
        r"Added \1 \2 (\4) to \3's Udhaar Khata (not counted in collected revenue yet).",
    ),
    (
        re.compile(r"^([\d.]+) (.+?) (₹[\d,]+) ke rate par receive hui hain \(Total (₹[\d,]+)\)\.$"),
        r"Received \1 \2 at \3 per unit (Total \4).",
    ),
    (
        re.compile(r"^(.+?) se (₹[\d,]+) \((.+?)\) receive ho gaya aur Sales ledger mein include ho gaya\. Remaining balance: (₹[\d,]+)\.$"),
        r"Received \2 (\3) from \1 and updated the Sales ledger. Remaining balance: \4.",
    ),
    (
        re.compile(r"^Sale payment update ho gaya: (₹[\d,]+) \((.+?) → (.+?)\)\.$"),
        r"Updated sale payment: \1 (\2 → \3).",
    ),
    (
        re.compile(r"^Sale correct ho gayi: ([\d.]+) se ([\d.]+) \((₹[\d,]+)\)\. Audit trail updated\.$"),
        r"Corrected sale quantity from \1 to \2 (\3). Audit trail updated.",
    ),
    (
        re.compile(r"^([\d.]+) (.+?) (damage|expiry) mark ho gaya\. Remaining stock: ([\d.]+)\.$"),
        r"Marked \1 \2 as \3. Remaining stock: \4.",
    ),
    (
        re.compile(r"^(.+?) ka (damage|expiry) update ho gaya: ([\d.]+) se ([\d.]+)\. Remaining stock: ([\d.]+)\.$"),
        r"Updated \2 for \1 from \3 to \4. Remaining stock: \5.",
    ),
    (
        re.compile(r"^(.+?) ka stock receive update ho gaya: ([\d.]+) se ([\d.]+) \(Rate (₹[\d,]+)\)\. Remaining stock: ([\d.]+)\.$"),
        r"Updated stock receipt for \1 from \2 to \3 (Rate \4). Remaining stock: \5.",
    ),
    (
        re.compile(r"^(.+?) inventory mein nahi mila — kya naya product add karun\?$"),
        r"\1 was not found in inventory — should I add it as a new product?",
    ),
    (
        re.compile(r"^'(.+?)' ke (\d+) options mile: (.+?) \((.+?)\)\. Screen se select karein ya exact naam bolein\.$"),
        r"Found \2 options for '\1': \3 (\4). Tap one on screen or speak the exact name.",
    ),
    (
        re.compile(r"^Awaaz clear nahi thi ya background noise zyada tha\. Kripya dobara bolein\.$"),
        r"Audio wasn't clear or there was too much background noise. Please try again.",
    ),
    (
        re.compile(r"^Theek hai, pichla step cancel kar diya gaya\.$"),
        r"Okay, cancelled the previous step.",
    ),
    (
        re.compile(r"^Kripya item aur quantity saaf bolein\.$"),
        r"Please state the item and quantity clearly.",
    ),
]


def localize_reply_sync(text: str, target_lang: str) -> str:
    if not text or target_lang == "hinglish":
        return text
    if target_lang == "en":
        for pat, repl in _EN_PATTERNS:
            if pat.match(text):
                out = pat.sub(repl, text)
                out = out.replace(", jinmein se ", ", with ").replace(" low-stock hain.", " low in stock.")
                out = out.replace(" aur sabhi stock healthy hain.", " and all stock levels are healthy.")
                return out
    return text


async def localize_reply_async(text: str, target_lang: str) -> str:
    """Strictly translates reply into English ('en') or Hindi Devanagari ('hi'), keeping Hinglish untouched."""
    if not text or target_lang not in {"en", "hi"}:
        return text

    fast = localize_reply_sync(text, target_lang)
    if target_lang == "en" and fast != text:
        return fast

    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        return fast

    lang_desc = "clear, natural Indian English" if target_lang == "en" else "natural Hindi written in Devanagari script (हिंदी)"
    prompt = (
        f"Translate the following shopkeeper assistant message into {lang_desc}. "
        "Preserve all numbers, ₹ amounts, product names (e.g. Maggie Masala 70 Gram, Coca-Cola 750 Ml), "
        "customer names, and 'Cash'/'Online'/'Udhaar' terms accurately. Output ONLY the translated text.\n\n"
        f"{text}"
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.0},
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            translated = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            if translated:
                return translated
    except Exception as exc:
        logger.debug("Reply localization skipped: %s", exc)
    return fast
