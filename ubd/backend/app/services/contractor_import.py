"""Импорт контрагентов из Excel-выгрузки базы Синапс (девелоперы/генподрядчики).

Понимает формат export/девелоперы_генподрядчики_синапс.xlsx:
- листы «Дмитрий — Девелоперы» / «Дмитрий — Генподрядчики» (Название, Оборот за 2025, …)
- и лист «Все данные» (Категория, ИНН, ОГРН, …).
Маппинг: Девелопер → тип «Заказчик», Генподрядчик → тип «ГП».
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy.orm import Session

from ..models import Contractor

TYPE_BY_CATEGORY = {"Девелопер": "Заказчик", "Генподрядчик": "ГП"}


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def map_row(values: dict) -> dict | None:
    inn = _digits(values.get("ИНН"))
    name = str(values.get("Название") or "").strip()
    if not inn and not name:
        return None
    category = str(values.get("Категория") or "")
    phones = str(values.get("Телефоны") or values.get("Телефон") or "")
    emails = str(values.get("Почта") or values.get("Email") or "")
    director = str(values.get("Руководитель") or values.get("Ген. директор") or "")
    revenue_raw = (values.get("Оборот 2025, ₽") or values.get("Оборот за 2025, ₽")
                   or values.get("Оборот 2025") or "")
    try:
        revenue = int(round(float(re.sub(r"[^\d]", "", str(revenue_raw)) or 0)))
    except ValueError:
        revenue = 0
    return {
        "name": name or f"ИНН {inn}",
        "inn": inn,
        "ogrn": _digits(values.get("ОГРН")),
        "legal_address": str(values.get("Юр. адрес") or ""),
        "city": str(values.get("Город / регион") or ""),
        "director": director.split("\n")[0][:200],
        "phone": phones.split("\n")[0][:200],
        "email": emails.split("\n")[0][:300],
        "contract_type": TYPE_BY_CATEGORY.get(category, "Прочие"),
        "revenue_2025": revenue or None,
        "egrul_status": str(values.get("Статус") or "")[:40],
        "sro_name": str(values.get("СРО") or "")[:300],
        "source": "Синапс",
    }


def import_rows(db: Session, row_dicts: Iterable[dict]) -> tuple[int, int, int]:
    """Вставка/обновление по ИНН. Возвращает (новых, обновлено, пропущено)."""
    from sqlalchemy import select

    existing: dict[str, Contractor] = {}
    for c in db.execute(select(Contractor).where(Contractor.inn != "")).scalars():
        existing[c.inn] = c

    created = updated = skipped = 0
    for mapped in row_dicts:
        if mapped is None:
            skipped += 1
            continue
        current = existing.get(mapped["inn"]) if mapped["inn"] else None
        if current is None:
            contractor = Contractor(**mapped)
            db.add(contractor)
            if mapped["inn"]:
                existing[mapped["inn"]] = contractor
            created += 1
        else:
            for key, value in mapped.items():
                if value and not getattr(current, key):
                    setattr(current, key, value)
            if mapped["revenue_2025"]:
                current.revenue_2025 = mapped["revenue_2025"]
            updated += 1
    db.flush()
    return created, updated, skipped


def import_workbook(db: Session, wb, cap_per_sheet: int | None = None,
                    sheet_names: Iterable[str] | None = None) -> tuple[int, int, int]:
    """Импорт из открытой книги openpyxl (read_only, data_only)."""
    from openpyxl.utils.exceptions import InvalidFileException  # noqa: F401

    created = updated = skipped = 0
    for sheet in wb.worksheets:
        if sheet_names is not None and sheet.title not in sheet_names:
            continue
        rows = sheet.iter_rows(values_only=True)
        try:
            header = [str(h).strip() if h is not None else "" for h in next(rows)]
        except StopIteration:
            continue
        if "ИНН" not in header:
            continue
        col = {h: i for i, h in enumerate(header) if h}
        count = 0
        batch = []
        for values_tuple in rows:
            if cap_per_sheet is not None and count >= cap_per_sheet:
                break
            values = {h: values_tuple[i] if i < len(values_tuple) else None
                      for h, i in col.items()}
            batch.append(map_row(values))
            count += 1
        c, u, s = import_rows(db, batch)
        created += c
        updated += u
        skipped += s
    db.flush()
    return created, updated, skipped
