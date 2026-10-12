import pytest

from app import auth


@pytest.fixture
def exposed(make_client, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_FAILURE_DELAY", 0)
    return make_client(bind="0.0.0.0", password="mot-de-passe", secret="s" * 32)


def test_local_mode_needs_no_login(make_client):
    client = make_client()
    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/health").json()["authenticated"] is True


def test_api_requires_login_when_exposed(exposed):
    response = exposed.get("/api/jobs")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentification requise"
    health = exposed.get("/api/health").json()
    assert health["auth_required"] is True and health["authenticated"] is False


def test_login_flow(exposed):
    wrong = exposed.post("/api/login", json={"password": "faux"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == "Mot de passe incorrect"
    assert exposed.post("/api/login", json={"password": "mot-de-passe"}).status_code == 204
    assert exposed.get("/api/jobs").status_code == 200
    assert exposed.get("/api/health").json()["authenticated"] is True
    assert exposed.post("/api/logout").status_code == 204
    assert exposed.get("/api/jobs").status_code == 401


def test_forged_cookie_is_rejected(exposed):
    exposed.cookies.set("jideo_session", "forge")
    assert exposed.get("/api/jobs").status_code == 401
