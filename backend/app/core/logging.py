import logging
import re

_SECRET_PATTERN = re.compile(
    r"(Bearer\s+[A-Za-z0-9\-_\.]+|gsk_[A-Za-z0-9]+|AIza[A-Za-z0-9\-_]+|AQ\.[A-Za-z0-9\-_]+|sb_secret_[A-Za-z0-9\-_]+)"
)
_PHONE_PATTERN = re.compile(r"(\+91[\-\s]?)?\b[6-9]\d{9}\b")


def redact_pii(text: str) -> str:
    cleaned = _SECRET_PATTERN.sub("[REDACTED_SECRET]", text)
    cleaned = _PHONE_PATTERN.sub("[REDACTED_PHONE]", cleaned)
    return cleaned


class PiiSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return redact_pii(rendered)


def get_logger(name: str = "cue") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            PiiSafeFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
