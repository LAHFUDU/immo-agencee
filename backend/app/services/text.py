import re
import unicodedata


def normalize_key(value: str | None) -> str | None:
    """Accent/case/spacing-insensitive key, so 'Salé', 'sale ' and 'SALE' compare equal."""
    if value is None:
        return None
    v = unicodedata.normalize("NFKD", value)
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = re.sub(r"[\s\-_'’.]+", " ", v.lower()).strip()
    return v or None


def phone_key(phone: str | None) -> str | None:
    """Digits-only phone key; Moroccan +212/00212 prefixes are folded into the national 0 form."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("212") and len(digits) == 12:
        digits = "0" + digits[3:]
    return digits or None


def like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
