from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo


def get_business_today(timezone_name: str = "Asia/Kolkata") -> date:
    tz = ZoneInfo(timezone_name)
    return datetime.now(tz).date()


def get_business_now_iso(timezone_name: str = "Asia/Kolkata") -> str:
    tz = ZoneInfo(timezone_name)
    return datetime.now(tz).isoformat()


def check_memory_window_days(
    target_date: date,
    reference_today: date | None = None,
    window_days: int = 30,
) -> tuple[bool, int]:
    """Return (within_window, days_ago). Strictly enforces the 30-day rolling chat window."""
    today = reference_today or get_business_today()
    delta = (today - target_date).days
    return (delta <= window_days, delta)


def detect_over_30_day_reference(text: str, reference_today: date | None = None) -> int | None:
    """
    Detect conversational references older than 30 days (1 month), such as:
    - "do mahine pehle", "2 mahine pehle", "2 months ago", "3 months back"
    - "45 din pehle", "60 days ago", "pichle saal", "last year"
    Returns estimated days_ago if > 30 days, else None.
    """
    lower = text.lower()
    if re.search(r"\b(pichle\s+saal|last\s+year|ek\s+saal\s+pehle|1\s+year\s+ago)\b", lower):
        return 365

    month_word_map = {
        "do": 2,
        "teen": 3,
        "char": 4,
        "chaar": 4,
        "paanch": 5,
        "chhe": 6,
        "two": 2,
        "three": 3,
        "four": 4,
    }
    m_num = re.search(r"\b(\d+)\s*(mahine|mahina|months?)\s*(pehle|ago|back|purana|purani)?\b", lower)
    if m_num:
        months = int(m_num.group(1))
        if months >= 2:
            return months * 30

    m_word = re.search(
        r"\b(do|teen|char|chaar|paanch|chhe|two|three|four)\s*(mahine|mahina|months?)\b",
        lower,
    )
    if m_word:
        return month_word_map.get(m_word.group(1), 2) * 30

    d_match = re.search(r"\b(\d+)\s*(din|days?)\s*(pehle|ago|back)\b", lower)
    if d_match:
        days = int(d_match.group(1))
        if days > 30:
            return days

    return None


def resolve_relative_date(
    expr: str | None,
    timezone_name: str = "Asia/Kolkata",
) -> date:
    """Resolve Hinglish/English relative date expressions into business calendar date."""
    today = get_business_today(timezone_name)
    if not expr:
        return today

    clean = expr.strip().lower()
    if clean in {"aaj", "today"} or re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
        if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
            try:
                return date.fromisoformat(clean)
            except ValueError:
                return today
        return today

    if clean in {"kal", "yesterday", "beeta kal"}:
        return today - timedelta(days=1)
    if clean in {"parso", "parsoh", "day before yesterday"}:
        return today - timedelta(days=2)
    if "last week" in clean or "pichle hafte" in clean:
        return today - timedelta(days=7)

    m = re.search(r"(\d+)\s*(din|days?)\s*(pehle|ago)", clean)
    if m:
        return today - timedelta(days=int(m.group(1)))

    return today
