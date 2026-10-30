"""Pure normalization helpers. Invalid money/time is quarantined, never rounded/guessed."""

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class QualityError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def vnd(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise QualityError("invalid_money") from exc
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value() or amount > 9223372036854775807:
        raise QualityError("non_integer_or_invalid_vnd")
    return int(amount)


def utc(value, origin):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    if origin is None or origin[0] != value:
        raise QualityError("missing_timestamp_origin")
    try:
        return value.replace(tzinfo=ZoneInfo(origin[1])).astimezone(UTC)
    except ZoneInfoNotFoundError as exc:
        raise QualityError("invalid_timestamp_zone") from exc


def public_text(value):
    if value is None:
        return None
    value = re.sub(r"https?://\S+", "[link]", value, flags=re.I)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
    return re.sub(r"(?<!\w)(?:\+?\d[\s().-]*){8,15}(?!\w)", "[phone]", value)


def label(value):
    return value if value and re.fullmatch(r"[\w.:-]{1,100}", value, re.ASCII) else "REDACTED"


def video_url(value):
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def dimensions(value):
    if not value:
        return None
    match = re.fullmatch(r"\s*([\d.]+)\s*[x×]\s*([\d.]+)\s*[x×]\s*([\d.]+)\s*(cm|mm|m)\s*", value, re.I)
    if not match:
        return None
    try:
        numbers = [float(match[index]) for index in range(1, 4)]
        if not all(number > 0 for number in numbers):
            return None
        return dict(zip(("length", "width", "height"), numbers, strict=True), unit=match[4].lower())
    except ValueError:
        return None


def document_id(entity, key):
    if entity == "system_log":
        date = datetime.fromisoformat(str(key["created_at"]))
        return f"system_log:{key['id']}:{date.isoformat(timespec='microseconds')}"
    return f"{entity}:{key['id']}"


def comparable(value):
    if isinstance(value, datetime):
        value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value.replace(microsecond=value.microsecond // 1000 * 1000)
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [comparable(item) for item in value]
    return value
