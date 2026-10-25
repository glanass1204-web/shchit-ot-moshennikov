"""Regression tests for public API input validation and response headers."""
from fastapi.testclient import TestClient
from analyzer import MAX_LEN
from main import app

client = TestClient(app)

def test_missing_text_is_rejected():
    assert client.post("/api/analyze", json={}).status_code == 422

def test_oversized_text_is_rejected():
    response = client.post("/api/analyze", json={"text": "a" * (MAX_LEN + 1)})
    assert response.status_code == 422

def test_invalid_text_type_is_rejected():
    response = client.post("/api/analyze", json={"text": {"bad": "value"}})
    assert response.status_code == 422

def test_health_response_is_not_cached():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"

def test_regular_check_does_not_call_ai():
    response = client.post("/api/analyze", json={"text": "Hello", "use_ai": False})
    assert response.status_code == 200
    assert "ai" not in response.json()
