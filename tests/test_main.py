from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_whoami_without_token_returns_401():
    response = client.get("/api/whoami")
    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] == "missing_token"
