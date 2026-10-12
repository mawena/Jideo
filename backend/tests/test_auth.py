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


def test_session_is_invalidated_by_password_change(make_client, monkeypatch):
    monkeypatch.setattr(auth, "LOGIN_FAILURE_DELAY", 0)
    first = make_client(bind="0.0.0.0", password="ancien", secret="s" * 32)
    assert first.post("/api/login", json={"password": "ancien"}).status_code == 204
    cookie = first.cookies.get("jideo_session")
    second = make_client(bind="0.0.0.0", password="nouveau", secret="s" * 32)
    second.cookies.set("jideo_session", cookie)
    assert second.get("/api/jobs").status_code == 401


def test_parallel_failures_are_serialized(make_client, monkeypatch):
    import asyncio
    import time

    import httpx

    monkeypatch.setattr(auth, "LOGIN_FAILURE_DELAY", 0.2)
    monkeypatch.setattr(auth, "_failure_lock", None)
    app = make_client(bind="0.0.0.0", password="mot-de-passe", secret="s" * 32).app

    async def attempt(client, password):
        return await client.post("/api/login", json={"password": password})

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.monotonic()
            wrong = await asyncio.gather(*(attempt(client, "faux") for _ in range(5)))
            failures = time.monotonic() - started
            started = time.monotonic()
            good = await attempt(client, "mot-de-passe")
            return wrong, failures, good, time.monotonic() - started

    wrong, failures, good, good_time = asyncio.run(scenario())
    assert all(r.status_code == 401 for r in wrong)
    assert failures >= 0.9
    assert good.status_code == 204 and good_time < 0.15
