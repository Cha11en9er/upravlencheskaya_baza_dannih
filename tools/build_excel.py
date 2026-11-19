"""
Сборка сводного Excel по базам девелоперов и генподрядчиков (данные Synaps).

Вход:  data/synaps/{developers,genpodryad}/companies.json (+ shortlist.json как источник
       названий, региона, юр. статуса, ОГРН, СРО).
Выход: export/девелоперы_генподрядчики_синапс.xlsx

Листы:
  1. Все данные             — обе категории, все поля, включая строки с ошибками парсинга
  2. Девелоперы             — детально, только успешные карточки
  3. Генподрядчики          — детально, только успешные карточки
  4. Дмитрий — Девелоперы   — под запрос Дмитрия: оборот 2025 > 0, есть телефон или почта
  5. Дмитрий — Генподрядчики— то же для генподрядчиков

Запуск:
    python tools/build_excel.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "synaps"
OUT = ROOT / "export" / "девелоперы_генподрядчики_синапс.xlsx"

# Генподряд: шесть выгрузок Synaps (шортлист + два потока + три потока остатка).
# Пересечений по ИНН по построению нет, но мержим с приоритетом ok-записей.
GEN_COMPANY_FILES = [
    "companies.json",
    "companies_part1.json",
    "companies_part2.json",
    "companies_remain_part1.json",
    "companies_remain_part2.json",
    "companies_remain_part3.json",
]

HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP_TOP = Alignment(wrap_text=True, vertical="top", horizontal="left")
TOP = Alignment(vertical="top", horizontal="left")
NUM_FMT = "#,##0"

# Единый набор колонок для «Все данные» и листов категорий.
# (ключ, заголовок, ширина, перенос_текста)
BASE_COLUMNS: list[tuple[str, str, int, bool]] = [
    ("inn", "ИНН", 14, False),
    ("ogrn", "ОГРН", 14, False),
    ("name", "Название", 36, False),
    ("status", "Статус", 16, False),
    ("rev2025", "Оборот 2025, ₽", 15, False),
    ("rev2024", "Оборот 2024, ₽", 15, False),
    ("rev2023", "Оборот 2023, ₽", 15, False),
    ("trend", "Динамика выручки", 14, False),
    ("phones", "Телефоны", 24, True),
    ("emails", "Почта", 28, True),
    ("okved", "ОКВЭД", 34, True),
    ("region", "Город / регион", 18, False),
    ("legal_address", "Юр. адрес", 42, True),
    ("registration_date", "Дата регистрации", 14, False),
    ("authorized_capital", "Уставный капитал", 14, False),
    ("headcount", "Численность", 11, False),
    ("general_director", "Руководитель", 30, True),
    ("reliability", "Надёжность", 12, False),
    ("enforcement_debt", "Исп. производства", 30, True),
    ("bank_account_state", "Банк. счета", 12, False),
    ("sro_name", "СРО", 34, True),
    ("member_status", "Членство СРО", 14, False),
    ("sro_members", "Членов в СРО", 12, False),
    ("profile_url", "Ссылка Synaps", 30, False),
]

DMITRY_COLUMNS: list[tuple[str, str, int, bool]] = [
    ("name", "Название", 36, False),
    ("rev2025", "Оборот за 2025, ₽", 16, False),
    ("phones", "Телефон", 24, True),
    ("emails", "Почта", 30, True),
    ("inn", "ИНН", 14, False),
    ("ogrn", "ОГРН", 14, False),
    ("status", "Статус", 16, False),
    ("region", "Город / регион", 18, False),
    ("legal_address", "Юр. адрес", 42, True),
    ("okved", "ОКВЭД", 34, True),
    ("rev2024", "Оборот 2024, ₽", 15, False),
    ("rev2023", "Оборот 2023, ₽", 15, False),
    ("trend", "Динамика выручки", 14, False),
    ("headcount", "Численность", 11, False),
    ("general_director", "Руководитель", 30, True),
    ("reliability", "Надёжность", 12, False),
    ("enforcement_debt", "Исп. производства", 30, True),
    ("authorized_capital", "Уставный капитал", 14, False),
    ("bank_account_state", "Банк. счета", 12, False),
    ("sro_name", "СРО", 34, True),
    ("member_status", "Членство СРО", 14, False),
    ("profile_url", "Ссылка Synaps", 30, False),
]

NUMERIC_KEYS = {"rev2023", "rev2024", "rev2025", "sro_members", "headcount"}

# Сводный лист: категория в начале, ошибка парсинга в конце.
ALL_COLUMNS = [("category", "Категория", 14, False)] + BASE_COLUMNS + \
    [("error", "Ошибка парсинга", 20, True)]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").strip()


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _to_int(value: Any) -> int | None:
    """'12 345 678 ₽' -> 12345678; '-', '', None -> None; '0' -> 0."""
    text = _clean(value)
    if not text or text == "-":
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def load_shortlist_meta(category_dir: Path) -> dict[str, dict[str, str]]:
    """ИНН -> метаданные из shortlist.json (название, регион, статус, ОГРН, СРО)."""
    out: dict[str, dict[str, str]] = {}
    raw = json.loads((category_dir / "shortlist.json").read_text(encoding="utf-8"))
    for item in raw.get("items", []):
        inn = _digits(item.get("inn"))
        if not inn:
            continue
        out[inn] = {
            "name": _clean(
                item.get("title")
                or item.get("short_name")
                or item.get("full_name")
                or item.get("query_name")
                or item.get("name")
            ),
            "status": _clean(item.get("status")),
            "region": _clean(item.get("region")),
            "ogrn": _digits(item.get("ogrn")),
            "okved": _clean(item.get("okved")),
            "okved_name": _clean(item.get("okved_name")),
            "sro_name": _clean(item.get("sro_name")),
            "sro_members": item.get("sro_members"),
        }
    return out


def load_registry_index() -> dict[str, dict[str, str]]:
    """Индекс НОСТРОЙ (tools/make_registry_index.py): ИНН -> имя/регион/СРО."""
    path = DATA / "genpodryad" / "registry_index.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(category_dir: Path, files: list[str] | None = None,
              registry: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """companies.json категории -> плоские строки (включая ошибки парсинга).

    При нескольких файлах мержит по ИНН, приоритет — записи без ошибки.
    registry (НОСТРОЙ) дополняет имя/регион/СРО там, где shortlist не покрывает.
    """
    meta = load_shortlist_meta(category_dir)
    rows_by_inn: dict[str, dict[str, Any]] = {}
    for fname in files or ["companies.json"]:
        raw = json.loads((category_dir / fname).read_text(encoding="utf-8"))
        for item in raw.get("items", []):
            inn = _digits(item.get("inn"))
            m = meta.get(inn, {})
            reg = (registry or {}).get(inn, {})
            data: dict[str, Any] = item.get("data") if isinstance(item.get("data"), dict) else {}

            okved = _clean(data.get("okved"))
            if not okved:
                short_okved = m.get("okved", "")
                okved_name = m.get("okved_name", "")
                okved = f"{short_okved} {okved_name}".strip()

            name = reg.get("name") or m.get("name", "")
            row = {
                "inn": inn,
                "ogrn": m.get("ogrn", ""),
                "name": name or f"ИНН {inn}",
                "status": m.get("status", ""),
                "rev2025": _to_int(data.get("revenue_2025")),
                "rev2024": _to_int(data.get("revenue_2024")),
                "rev2023": _to_int(data.get("revenue_2023")),
                "trend": _clean(data.get("revenue_trend")),
                "phones": _clean(data.get("phones")),
                "emails": _clean(data.get("emails")),
                "okved": okved,
                "region": reg.get("region") or m.get("region", ""),
                "legal_address": _clean(data.get("legal_address")),
                "registration_date": _clean(data.get("registration_date")),
                "authorized_capital": _clean(data.get("authorized_capital")),
                "headcount": _to_int(data.get("headcount")),
                "general_director": _clean(data.get("general_director")),
                "reliability": _clean(data.get("reliability")),
                "enforcement_debt": _clean(data.get("enforcement_debt")),
                "bank_account_state": _clean(data.get("bank_account_state")),
                "sro_name": reg.get("sro_name") or m.get("sro_name", ""),
                "member_status": reg.get("member_status", ""),
                "sro_members": m.get("sro_members"),
                "profile_url": _clean(item.get("profile_url")),
                "error": _clean(item.get("error")).split("\n")[0][:160] if item.get("status") != "ok" else "",
            }
            prev = rows_by_inn.get(inn)
            if prev is None or (prev["error"] and not row["error"]):
                rows_by_inn[inn] = row
    return list(rows_by_inn.values())


def is_active(row: dict[str, Any]) -> bool:
    """Статус неизвестен (генподрядчики) или организация действующая."""
    status = row["status"].lower()
    return (not status) or status.startswith("действ")


def dmitry_filter(row: dict[str, Any]) -> bool:
    """Оборот 2025 > 0, организация действующая, есть телефон или почта."""
    return (
        bool(row["rev2025"])
        and is_active(row)
        and (bool(row["phones"]) or bool(row["emails"]))
    )


def sort_key(row: dict[str, Any]):
    return (-(row["rev2025"] or 0), row["name"].lower())


def write_sheet(ws, columns: list[tuple[str, str, int, bool]], rows: list[dict[str, Any]],
                extra_first: list[tuple[str, str, int]] = ()) -> None:
    headers = [label for _, label, _, _ in columns]
    for key, label, _w in extra_first:
        headers.insert(0, label)
    for col, label in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")

    keys = [key for key, *_ in columns]
    for r, row in enumerate(rows, start=2):
        values: list[Any] = []
        for key, _label, _w, _wrap in columns:
            v = row.get(key)
            values.append("" if v is None else v)
        for key, _label, _w in extra_first:
            values.insert(0, row.get(key, ""))
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.alignment = TOP
        # порядок экстра-колонок совпадает с категорией листа «Все данные»

    widths = [w for _k, _label, w, *_ in extra_first] + [w for _k, _l, w, _wrap in columns]
    wrap_flags = [False] * len(extra_first) + [wrap for _k, _l, _w, wrap in columns]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    numeric_cols = [i for i, key in enumerate([""] * len(extra_first) + keys, start=1)
                    if key in NUMERIC_KEYS]
    for r in range(2, len(rows) + 2):
        for c in numeric_cols:
            ws.cell(row=r, column=c).number_format = NUM_FMT
        for c, wrap in enumerate(wrap_flags, start=1):
            if wrap:
                ws.cell(row=r, column=c).alignment = WRAP_TOP

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(len(rows) + 1, 1)}"


def _repack_max_compression(path: Path) -> None:
    """Пересжатие xlsx (openpyxl пишет zip с дефолтным уровнем; лимит панели — 100 МиБ)."""
    import os
    import zipfile

    tmp = str(path) + ".tmp"
    with zipfile.ZipFile(path) as zin, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
    os.replace(tmp, path)


def main() -> None:
    dev_rows = load_rows(DATA / "developers")
    gen_rows = load_rows(DATA / "genpodryad", files=GEN_COMPANY_FILES,
                         registry=load_registry_index())

    dev_ok = [r for r in dev_rows if not r["error"]]
    gen_ok = [r for r in gen_rows if not r["error"]]
    dev_dmitry = sorted(filter(dmitry_filter, dev_ok), key=sort_key)
    gen_dmitry = sorted(filter(dmitry_filter, gen_ok), key=sort_key)

    all_rows = ([{**r, "category": "Девелопер"} for r in dev_rows]
                + [{**r, "category": "Генподрядчик"} for r in gen_rows])

    wb = Workbook()
    ws_all = wb.active
    ws_all.title = "Все данные"
    write_sheet(ws_all, ALL_COLUMNS, all_rows)

    ws_dev = wb.create_sheet("Девелоперы")
    write_sheet(ws_dev, BASE_COLUMNS, sorted(dev_ok, key=sort_key))

    ws_gen = wb.create_sheet("Генподрядчики")
    write_sheet(ws_gen, BASE_COLUMNS, sorted(gen_ok, key=sort_key))

    ws_ddev = wb.create_sheet("Дмитрий — Девелоперы")
    write_sheet(ws_ddev, DMITRY_COLUMNS, dev_dmitry)

    ws_dgen = wb.create_sheet("Дмитрий — Генподрядчики")
    write_sheet(ws_dgen, DMITRY_COLUMNS, gen_dmitry)

    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    _repack_max_compression(OUT)

    overlap = len({r["inn"] for r in dev_ok} & {r["inn"] for r in gen_ok})
    print(f"OK -> {OUT}")
    print(f"Все данные: {len(all_rows)} строк (дев {len(dev_rows)} + ген {len(gen_rows)}), "
          f"ошибок: {len(dev_rows) - len(dev_ok) + len(gen_rows) - len(gen_ok)}, пересечение ИНН: {overlap}")
    print(f"Дмитрий — девелоперы: {len(dev_dmitry)}; генподрядчики: {len(gen_dmitry)}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
