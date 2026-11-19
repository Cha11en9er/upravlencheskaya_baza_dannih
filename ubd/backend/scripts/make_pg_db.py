"""Переход МВП на PostgreSQL: создание базы и роли из superuser-пароля.

МВП сейчас работает на SQLite (см. docs/SETUP.md). Когда будет известен пароль
postgres (или отдельный superuser), этот скрипт создаст базу `ubd` и роль
`ubd_app` с правами только на неё. Затем — две строки в ubd/backend/.env и
первый запуск приложения (таблицы создадутся сами, сид выполнится).

Запуск:
    python scripts/make_pg_db.py <пароль_postgres> [--host 127.0.0.1] [--port 5432]
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    import psycopg

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    pg_password = args[0]
    host = "127.0.0.1"
    port = 5432
    for flag, key in (("--host", "host"), ("--port", "port")):
        if flag in sys.argv:
            vals = sys.argv[sys.argv.index(flag) + 1]
            host = vals if key == "host" else int(vals)

    app_password = secrets.token_urlsafe(18)
    with psycopg.connect(f"host={host} port={port} dbname=postgres user=postgres password={pg_password}") as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname='ubd_app'")
            if cur.fetchone() is None:
                cur.execute(f"CREATE ROLE ubd_app LOGIN PASSWORD '{app_password}'")
            else:
                cur.execute(f"ALTER ROLE ubd_app WITH LOGIN PASSWORD '{app_password}'")
            cur.execute("SELECT 1 FROM pg_database WHERE datname='ubd'")
            if cur.fetchone() is None:
                cur.execute("CREATE DATABASE ubd OWNER ubd_app")
            else:
                cur.execute("ALTER DATABASE ubd OWNER TO ubd_app")

    print("OK. Добавьте в ubd/backend/.env:")
    print(f"UBD_DB_URL=postgresql+psycopg://ubd_app:{app_password}@{host}:{port}/ubd")
    print("Затем запустите приложение — таблицы и сид создадутся автоматически.")
    print("Пароль роли сохранён только в выводе выше — положите его в .env.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
