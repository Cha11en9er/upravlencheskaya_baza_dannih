"""Разбор значений HTML-форм (даты/числа/чекбоксы) — безопасные дефолты."""
from __future__ import annotations

from datetime import date, datetime


def parse_date(value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value: str | None) -> int:
    try:
        return int(round(float((value or "0").replace(" ", "").replace("\xa0", ""))))
    except (TypeError, ValueError):
        return 0


def parse_float(value: str | None) -> float:
    try:
        return float((value or "0").replace(" ", "").replace("\xa0", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def parse_bool(value: str | None) -> bool:
    return (value or "").lower() in ("on", "true", "1", "да")


def parse_id(value: str | None) -> int | None:
    try:
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None
