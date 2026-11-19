"""Авторизация и права (ТЗ 2.1.1, 1.2 п.2, 2.1.2)."""


def test_unauthenticated_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    resp = client.get("/contracts", follow_redirects=False)
    assert resp.status_code == 303


def test_login_wrong_credentials(client):
    resp = client.post("/login", data={"email": "admin@ubd.local", "password": "nope"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert "Неверный email или пароль" in resp.text


def test_simple_admin_login(client):
    """Простой вход «админ / 1» (МВП, см. DECISIONS.md)."""
    resp = client.post("/login", data={"email": "админ", "password": "1"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    # неверный пароль не пускает
    resp2 = client.post("/login", data={"email": "админ", "password": "2"},
                        follow_redirects=False)
    assert resp2.headers["location"] == "/login?error=1"


def test_login_admin_and_dashboard(admin_client):
    resp = admin_client.get("/")
    assert resp.status_code == 200
    assert "УБД" in resp.text
    assert "Администратор" in resp.text


def test_financier_cannot_open_admin(fin_client):
    resp = fin_client.get("/admin/users")
    assert resp.status_code == 403


def test_financier_contracts_read_only(fin_client):
    # Финансист: договоры — чтение → форма создания отдаёт 403
    resp = fin_client.get("/contracts/new")
    assert resp.status_code == 403
    resp = fin_client.get("/contracts")
    assert resp.status_code == 200


def test_financier_can_edit_payments(fin_client):
    resp = fin_client.get("/payments/new")
    assert resp.status_code == 200


def test_logout(client):
    client.post("/login", data={"email": "admin@ubd.local", "password": "admin123"})
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    resp = client.get("/", follow_redirects=False)
    assert resp.headers["location"] == "/login"
