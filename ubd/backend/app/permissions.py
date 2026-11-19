"""Роли (17 из ТЗ), блоки, уровни доступа и дефолтные матрицы."""
from __future__ import annotations

# 17 ролей из ТЗ п.1.2 п.3
ROLES: list[str] = [
    "Администратор", "ГИП", "ГАП", "Архитектор", "Руководитель проекта",
    "Сметчик", "Договорник", "МТО", "Технадзор", "Прораб",
    "Юрист", "Финансист", "Гл. бухгалтер", "СБ", "Секретарь",
    "Гендиректор", "Пользователь",
]

# Блоки из ТЗ п.2: ключ -> название плитки. value=False значит «МВП не реализован».
BLOCKS: dict[str, tuple[str, bool]] = {
    "budget": ("Бюджет и ГрП", True),
    "contracts": ("Договоры и Оплаты", True),
    "payments": ("Оплаты", True),
    "estimates": ("Сметы и Выполнение", False),
    "tenders": ("Тендеры и МТО", False),
    "smr": ("СМР и Графики", False),
    "quality": ("Качество и Надзор", False),
    "letters": ("Письма, Документооборот, Задачи", False),
    "reports": ("Отчеты", True),
}

EDIT, READ, NONE = "edit", "read", "none"
LEVEL_ORDER = {NONE: 0, READ: 1, EDIT: 2}


def normalize_access(access: dict | None) -> dict[str, str]:
    out = {}
    for key in BLOCKS:
        val = (access or {}).get(key, NONE)
        out[key] = val if val in LEVEL_ORDER else NONE
    return out


def default_access_for_role(role: str) -> dict[str, str]:
    """Дефолтная матрица по роли (админ переопределяет в админ-панели)."""
    if role == "Администратор":
        return normalize_access({k: EDIT for k in BLOCKS})
    if role == "Гендиректор":
        return normalize_access({k: READ for k in BLOCKS})
    if role == "Финансист" or role == "Гл. бухгалтер":
        return normalize_access({"budget": READ, "contracts": READ, "payments": EDIT, "reports": READ})
    if role == "Договорник" or role == "Юрист":
        return normalize_access({"contracts": EDIT, "payments": READ, "reports": READ})
    if role == "Руководитель проекта" or role == "ГИП" or role == "ГАП":
        return normalize_access({"budget": EDIT, "contracts": READ, "payments": READ, "reports": READ})
    if role == "Сметчик" or role == "МТО" or role == "Прораб" or role == "Технадзор":
        return normalize_access({"budget": READ, "contracts": READ, "payments": READ})
    if role == "Секретарь":
        return normalize_access({"payments": READ})
    return normalize_access({})


def access_level(access: dict, block: str) -> str:
    return normalize_access(access).get(block, NONE)
