# Журнал сборки МВП (что делалось и как проверялось)

2026-11-19, автономная сессия. Каждый пункт — «сделано → как проверено».

## Хронология

1. **Разведка окружения**: python 3.12.0, pip 24.0, PG18-служба running на :5432,
   PyPI доступен, node 22 (не нужен), порт 8000 свободен.
   Проверка: команды `--version`, `Get-Service`, `netstat`, `pip index versions`.
2. **venv + зависимости**: `python -m venv ubd/.venv`, установка из PyPI,
   версии зафиксированы в requirements.txt. Проверка: `pip freeze` (в SETUP.md).
3. **Попытка PostgreSQL**: pg_hba только scram-sha-256; пароль неизвестен,
   вариант postgres/postgres не подошёл → **перебор прекращён**, решение —
   SQLite через SQLAlchemy + скрипт перехода `scripts/make_pg_db.py`.
4. **Код бэкенда**: модели (9 таблиц), security (pbkdf2+PyJWT), permissions
   (17 ролей × 9 блоков), calc.py (правила ТЗ), services (recalc, changelog,
   export xlsx, импорт контрагентов), 8 роутеров, 16 шаблонов, CSS по палитре
   ТЗ, vanilla JS. Проверка: `python -m py_compile app/**/*.py` → OK.
5. **Сид**: админ + РП + Финансист; демо-проекты/договоры/оплаты/бюджет;
   импорт 998 контрагентов из выгрузки Синапс. Проверка: SQL-подсчёты строк,
   верх списка — Татнефть (1 379 916 414 ₽) с телефоном/почтой.
6. **Тесты** (pytest): 22 теста — калькуляции ТЗ, авторизация/403/редиректы,
   сценарии (договор→оплата→пересчёт, ДС подписано→договор обновлён,
   бюджет→риск/дата договора, удаление пустого, отказ удаления заполненного,
   журнал). Итог: **22 passed**.
7. **Смоук по живому серверу** (uvicorn + curl):
   - POST /login → 303 + cookie; страницы /, /contracts, /payments, /budget,
     /contractors, /reports, /admin/* → 200;
   - POST /contracts/new → 303, договор в БД и в списке;
   - POST /payments/new → 303, оплачено выросло до ₽ 8 650 000, остаток
     ₽ 25 150 000 — калькуляции сквозь HTTP сходятся;
   - GET /contracts/export.xlsx → 200, валидный xlsx (openpyxl читает);
   - создание пользователя через админку → 303, матрица прав применилась.

## Пойманные и исправленные баги (все — тестами/смоуком)

| Баг | Симптом | Фикс |
|---|---|---|
| recalc_contract читал кэшированную (пустую) коллекцию `contract.payments` | оплачено=0 после сида | сумма оплат через SQL `select sum(...)` |
| seed не флашил оплаты перед пересчётом (autoflush=False) | то же | `db.flush()` перед select |
| seed не пересчитывал договоры после оплат | paid=0 | recalc_contract после оплат |
| `request` без импорта `Request` в dashboard.py (future annotations) | 422 missing query param `request` на GET / | добавлен импорт; правило — всегда импортировать Request |
| строковая аннотация `request: "Request"` в auth | то же | обычная аннотация |
| Request+Form в синхронном POST /login ломал разбор | 422 | PRG: POST /login без Request, ошибка через ?error=1 |
| мой regex-фикс удалил `request` у async-обработчиков с `await request.form()` | NameError | параметр возвращён скриптом точечно |
| TestClient starlette 1.10 deprecated с httpx | нестабильные ошибки | dev-зависимость httpx2 2.16.2 |
| у Contract не было relationship `contractor` | 500 на экспорте | relationship в модели |
| admin/users.html не получал `user` | 500 | `_user_context` передаёт user; `current.id`→`user.id` |
| тесты ждали 303 после login, а TestClient следует редиректам | ложные провалы | follow_redirects=False в conftest |
| тест делил на границу риска ровно 10% | 'yellow' != 'red' | по ТЗ ровно 10% — жёлтый; красный > 10% |

## Текущее состояние

- Сервер **оставлен запущенным** (uvicorn, 127.0.0.1:8000) — если выключился:
  `run_ubd.bat`.
- База: `ubd/backend/ubd.db` (SQLite). Вход: admin@ubd.local / admin123
  (сменить!), rp@ubd.local / user123, fin@ubd.local / user123.
- Тесты: 22 passed. Дальше — см. MVP_SCOPE.md «следующие спринты».
