"""Простой вход: создаёт/обновляет пользователя «админ» с паролем «1» (временно, для МВП).

Запуск из ubd/backend (берёт .env окружения):
    ../.venv/bin/python scripts/set_simple_admin.py            # локально/сервер
    python scripts/set_simple_admin.py --login админ --password 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.permissions import default_access_for_role  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", default="админ")
    parser.add_argument("--password", default="1")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == args.login)).scalar_one_or_none()
        if user is None:
            user = User(email=args.login, full_name="Администратор (простой вход)",
                        password_hash=hash_password(args.password),
                        role="Администратор", is_active=True,
                        block_access=default_access_for_role("Администратор"))
            db.add(user)
            action = "создан"
        else:
            user.password_hash = hash_password(args.password)
            user.role = "Администратор"
            user.block_access = default_access_for_role("Администратор")
            action = "обновлён"
        db.commit()
        print(f"Пользователь {action}: логин {args.login!r}, пароль задан")
    finally:
        db.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
