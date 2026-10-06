"""Сайт должен работать как раньше после подключения бота в main.py."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_analyze_returns_result_fields():
    resp = client.post("/api/analyze", json={"text": "Срочно переведи 5000 на карту"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["level"] == "high"
    for key in ("score", "level", "label", "verdict", "signs", "links", "recommendations", "highlights"):
        assert key in body
    assert "ai" not in body


def test_analyze_rejects_empty_text():
    assert client.post("/api/analyze", json={"text": ""}).status_code == 422


def test_login_page_serves_html():
    resp = client.get("/login")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Щит от мошенников" in resp.text


def test_index_serves_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
