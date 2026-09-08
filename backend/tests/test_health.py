"""Health endpoint test for the ECDAT backend."""

from fastapi.testclient import TestClient
from backend.app.main import app


def test_health_endpoint():
    """GET /health should return 200 + {"status": "ok"}."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}