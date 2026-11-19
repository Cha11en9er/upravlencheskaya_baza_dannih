"""
Индекс реестра НОСТРОЙ: members.jsonl -> registry_index.json

Собирает компактный справочник ИНН -> {имя, регион, СРО, членство} для всех
членов реестра. Нужен, потому что в выгрузках Synaps названий нет, а shortlist.json
покрывает только первые 3000 генподрядчиков.

Запуск (members.jsonl ищется в репозитории парсера):
    python tools/make_registry_index.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSER = Path(r"C:\repos\YouDo\18.04.26-synaps_parser")
SRC = PARSER / "genpodryad_comp" / "1_stage" / "members.jsonl"
OUT = ROOT / "data" / "synaps" / "genpodryad" / "registry_index.json"


def main() -> None:
    index: dict[str, dict[str, str]] = {}
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            inn = str(m.get("inn") or "").strip()
            if not inn:
                continue
            prev = index.get(inn)
            # Приоритет действующему членству; иначе первое вхождение.
            if prev is not None:
                prev_active = prev.get("member_status") == "Является членом"
                this_active = m.get("member_status") == "Является членом"
                if prev_active or not this_active:
                    continue
            index[inn] = {
                "name": (m.get("short_name") or m.get("full_name") or "").strip(),
                "full_name": (m.get("full_name") or "").strip(),
                "region": (m.get("region") or "").strip(),
                "sro_name": (m.get("sro_name") or "").strip(),
                "member_status": (m.get("member_status") or "").strip(),
            }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"OK -> {OUT}: {len(index)} ИНН")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
