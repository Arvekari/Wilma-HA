"""Timestamp parsing for Wilma's mixed date formats (ISO, Finnish, relative)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
ISO_LIKE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$")
UNIX_TS_RE = re.compile(r"^\d{10,13}$")
DATETIME_FI_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})$")
DATE_FI_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
SHORT_DATE_FI_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.$")

RELATIVE_DAYS = {
    "tänään": 0,
    "eilen": 1,
    "today": 0,
    "yesterday": 1,
    "idag": 0,
    "i dag": 0,
    "igår": 1,
    "i går": 1,
}


def _fallback() -> datetime:
    # Deterministic and old, so recency filters don't treat undated items as fresh.
    return datetime(1970, 1, 1)


def parse_wilma_timestamp(value: object) -> datetime:
    if value is None:
        return _fallback()

    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):  # NaN/inf guard
            return _fallback()
        millis = value if abs(value) >= 1_000_000_000_000 else value * 1000
        return datetime.fromtimestamp(millis / 1000)

    raw = str(value).strip()

    if ISO_DATETIME_RE.match(raw):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass

    m = ISO_LIKE_RE.match(raw)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        return datetime(y, mo, d, h, mi)

    if UNIX_TS_RE.match(raw):
        num = int(raw)
        return datetime.fromtimestamp(num if len(raw) == 10 else num / 1000)

    text = raw.lower().replace("klo", "").replace("julkaistu", "").strip()
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)

    for kw, days_ago in RELATIVE_DAYS.items():
        if kw in text:
            base = today - timedelta(days=days_ago)
            time_match = re.search(r"(\d{1,2})[:.](\d{2})", text)
            if time_match:
                h, mi = int(time_match.group(1)), int(time_match.group(2))
                base = base.replace(hour=h, minute=mi)
            return base

    m = DATETIME_FI_RE.match(text)
    if m:
        d, mo, y, h, mi = (int(x) for x in m.groups())
        return datetime(y, mo, d, h, mi)

    m = DATE_FI_RE.match(text)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        return datetime(y, mo, d)

    m = SHORT_DATE_FI_RE.match(text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        candidate = datetime(now.year, month, day)
        if candidate > today + timedelta(days=180):
            candidate = candidate.replace(year=candidate.year - 1)
        return candidate

    return _fallback()
