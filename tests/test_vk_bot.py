from collections import OrderedDict

import httpx
import pytest
from fastapi.testclient import TestClient

import bot_core
import vk_bot
from main import app

SCAM = "Ваша карта заблокирована. Переведите деньги на безопасный счёт. Продиктуйте код из СМС."


class FakeVK:
    """Подменяет HTTP-вызов к api.vk.com и запоминает отправленные сообщения."""

    def __init__(self):
        self.calls = []
        self.responses = []

    def __call__(self, url, data=None, timeout=None):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        resp = self.responses.pop(0) if self.responses else {"response": 1}
        if isinstance(resp, Exception):
            raise resp
        return httpx.Response(200, json=resp)

    @property
    def sent(self):
        return [c["data"] for c in self.calls if c["url"].endswith("messages.send")]


@pytest.fixture
def vk(monkeypatch):
    fake = FakeVK()
    monkeypatch.setattr(vk_bot.httpx, "post", fake)
    monkeypatch.setattr(vk_bot, "RETRY_DELAY", 0)
    monkeypatch.setattr(vk_bot, "_seen", OrderedDict())
    monkeypatch.setattr(vk_bot, "_hits", OrderedDict())
    monkeypatch.setattr(vk_bot, "_warned", {})
    monkeypatch.setattr(vk_bot, "token_status", "disabled")
    monkeypatch.setenv("VK_GROUP_TOKEN", "test-token")
    monkeypatch.setenv("VK_SECRET", "s3cret")
    monkeypatch.setenv("VK_CONFIRMATION", "abc123")
    return fake


client = TestClient(app)


def event(text=SCAM, event_id="e1", peer_id=111, from_id=111, secret="s3cret", **message):
    return {
        "type": "message_new",
        "event_id": event_id,
        "secret": secret,
        "object": {"message": {"text": text, "peer_id": peer_id, "from_id": from_id, **message}},
    }


def post(body):
    return client.post("/vk/callback", json=body)


# --- протокол Callback API -------------------------------------------------

def test_confirmation_returns_string(vk):
    resp = post({"type": "confirmation", "group_id": 1})
    assert (resp.status_code, resp.text) == (200, "abc123")


def test_wrong_secret_is_rejected_and_nothing_sent(vk):
    resp = post(event(secret="wrong"))
    assert resp.status_code == 403
    assert vk.sent == []


def test_missing_secret_config_rejects(vk, monkeypatch):
    monkeypatch.setenv("VK_SECRET", "")
    assert post(event(secret="")).status_code == 403


def test_bad_json_is_400(vk):
    resp = client.post("/vk/callback", content=b"not json")
    assert resp.status_code == 400


def test_other_event_types_are_acknowledged(vk):
    resp = post({"type": "message_reply", "secret": "s3cret", "object": {}})
    assert resp.text == "ok"
    assert vk.sent == []


# --- ответ пользователю ----------------------------------------------------

def test_message_gets_verdict_reply(vk):
    resp = post(event())
    assert resp.text == "ok"
    [sent] = vk.sent
    assert sent["peer_id"] == 111
    assert sent["message"].startswith("🔴 Похоже на мошенников")
    assert sent["v"] == vk_bot.API_VERSION
    assert vk.calls[0]["timeout"] == vk_bot.SEND_TIMEOUT


def test_duplicate_delivery_sends_once_with_stable_random_id(vk):
    post(event(event_id="dup"))
    post(event(event_id="dup"))
    assert len(vk.sent) == 1
    assert vk.sent[0]["random_id"] == vk_bot._random_id("dup")


def test_random_id_is_stable_and_31_bit():
    assert vk_bot._random_id("x") == vk_bot._random_id("x")
    assert 0 <= vk_bot._random_id("x") < 2**31


def test_chat_messages_are_ignored(vk):
    post(event(peer_id=2_000_000_005))
    assert vk.sent == []


def test_rate_limit_warns_once_then_resets(vk, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(vk_bot, "_now", lambda: clock[0])
    for i in range(12):
        post(event(text=f"привет {i}", event_id=f"r{i}"))
    texts = [s["message"] for s in vk.sent]
    assert len(texts) == 11
    assert texts[10] == vk_bot.RATE_LIMITED

    clock[0] += vk_bot.RATE_WINDOW + 1
    post(event(text="ещё", event_id="after"))
    assert vk.sent[-1]["message"] != vk_bot.RATE_LIMITED


def test_rate_limit_memory_is_bounded(vk, monkeypatch):
    monkeypatch.setattr(vk_bot, "RATE_MAX_USERS", 3)
    for user in range(10):
        post(event(text="привет", event_id=f"u{user}", peer_id=user + 1, from_id=user + 1))
    assert len(vk_bot._hits) <= 3


# --- сбои ------------------------------------------------------------------

def test_send_retries_once_after_timeout(vk):
    vk.responses = [httpx.ReadTimeout("slow")]
    post(event())
    assert len(vk.sent) == 2


def test_send_gives_up_after_second_failure_without_logging_text(vk, caplog):
    vk.responses = [httpx.ReadTimeout("slow"), {"error": {"error_code": 901}}]
    post(event())
    assert len(vk.sent) == 2
    assert SCAM not in caplog.text
    assert "messages.send failed" in caplog.text


def test_analyze_crash_sends_fallback_and_hides_text(vk, monkeypatch, capsys, caplog):
    def boom(text):
        raise RuntimeError(text)

    monkeypatch.setattr(bot_core, "analyze", boom)
    post(event())
    assert vk.sent[0]["message"] == bot_core.FAILED
    out = capsys.readouterr().out
    assert '"event": "error"' in out
    assert SCAM not in out + caplog.text


def test_metric_line_has_no_user_id_or_text(vk, capsys):
    post(event(from_id=424242, peer_id=424242))
    out = capsys.readouterr().out
    assert '"event": "check"' in out and '"level": "critical"' in out
    assert "424242" not in out and "карта" not in out


# --- проверка токена при старте ---------------------------------------------

def test_token_check_ok(vk):
    assert vk_bot.check_token() == "ok"
    assert vk.calls[0]["url"].endswith("groups.getById")


def test_token_check_error_shows_in_health(vk):
    vk.responses = [{"error": {"error_code": 5, "error_msg": "User authorization failed"}}]
    assert vk_bot.check_token() == "error"
    assert client.get("/api/health").json()["vk"] == "error"


def test_startup_runs_token_check(vk):
    with TestClient(app) as started:
        assert started.get("/api/health").json()["vk"] == "ok"


def test_token_check_disabled_without_token(vk, monkeypatch):
    monkeypatch.setenv("VK_GROUP_TOKEN", "")
    assert vk_bot.check_token() == "disabled"
    assert vk.calls == []
