# Сервер uchgrad-vps — заметки (без паролей!)

Обновлено: 19.11.26. Подключение: `ssh uchgrad-vps` — алиас из `~/.ssh/config`
на ноутбуке (root@201.34.143.208, ключ `~/.ssh/id_ed25519_uchgrad`).

## Машина

- Ubuntu (ядро 7.0.0-30-generic), x86_64; диск 38G (занято ~7.4G); RAM ~2 ГБ —
  впритык, другие приложения уже живут.
- Python 3.14.4, git 2.53, nginx 1.28.3 (sites: smartcamp, uchgrad.ru), docker нет.
- ufw выключен; порты прослушивания: 22, 53, 80, 443, 5432 (PostgreSQL 18.6),
  8000 (чужой uvicorn, 127.0.0.1), 8787 (чужой uvicorn 0.0.0.0), 10050 (zabbix).

## Наше приложение (УБД)

- Код: `/opt/ubd` (clone через deploy key `~/.ssh/id_ed25519_ubd_deploy`,
  read-only ключ в GitHub-репо `Cha11en9er/upravlencheskaya_baza_dannih`).
- Сервис: systemd `ubd.service` → uvicorn 0.0.0.0:8010, Restart=always.
  Логи: `journalctl -u ubd`.
- БД: серверный PostgreSQL 18.6 — база `ubd`, роль `ubd_app` (не superuser).
- Секреты на сервере (в git не попадают):
  - `/opt/ubd/ubd/backend/.env` — DB_URL, SECRET_KEY, админ-креды (600),
  - `/root/.ubd_admin_password` — пароль админа УБД (выдавался в чате 19.11.26),
  - `/root/.ubd_pg_password` — пароль роли ubd_app.
- Данные контрагентов: `/opt/ubd/export/девелоперы_генподрядчики_синапс.xlsx`
  (slim: только листы «Дмитрий — …», 24 МБ) — источник сида и импорта.
- Тесты на сервере: `cd /opt/ubd/ubd/backend && ../.venv/bin/python -m pytest
  tests -q` → 22 passed (тесты гоняются на временной sqlite, прод-базу не трогают).

## Деплой новой версии

```bash
git push origin main                              # локально
ssh uchgrad-vps
cd /opt/ubd && GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_ubd_deploy -o IdentitiesOnly=yes' git pull
cd ubd/backend && ../.venv/bin/python -m pytest tests -q   # опционально
systemctl restart ubd
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/login
```

Если менялись зависимости: `../.venv/bin/pip install -r backend/requirements.txt`
до рестарта.

## Смоук-чеклист (снаружи)

```
GET  http://201.34.143.208:8010/login      → 200
POST /login (креды из /root/.ubd_admin_password) → 303
GET  / , /contracts, /payments, /budget, /contractors, /reports, /admin/users → 200
GET  /contractors/export.xlsx → 200, application/vnd...spreadsheetml.sheet
```

## Грабли сервера

- RAM впритык: не запускать на сервере параллельные тяжёлые процессы, uvicorn —
  один worker (сейчас так и есть).
- Порт 8000 занят — наше приложение только на 8010.
- `git pull` на сервере — только с GIT_SSH_COMMAND и deploy-ключом (см. выше).
