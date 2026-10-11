from fastapi.testclient import TestClient

from app.main import create_app


def test_health(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
