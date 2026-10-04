import pytest

import bot_core
from analyzer import MAX_LEN, analyze
from bot_core import classify, collect_text, format_reply, handle

SCAM = "Ваша карта заблокирована. Переведите деньги на безопасный счёт. Продиктуйте код из СМС."


# --- сборка текста ---------------------------------------------------------

def test_collect_text_walks_forwards_replies_and_links():
    msg = {
        "text": "это правда?",
        "fwd_messages": [
            {"text": "первое", "fwd_messages": [{"text": "вложенное"}]},
            {"text": "", "attachments": [{"type": "link", "link": {"url": "http://sber-bank.xyz/login"}}]},
        ],
        "reply_message": {"text": "цитата"},
    }
    text = collect_text(msg)
    for part in ("это правда?", "первое", "вложенное", "цитата", "http://sber-bank.xyz/login"):
        assert part in text


def test_hidden_link_in_attachment_is_checked():
    msg = {"text": "Ваш приз", "attachments": [{"type": "link", "link": {"url": "http://sberbank-secure.xyz/login"}}]}
    reply = handle(msg)
    assert reply.event == "check"
    assert reply.level in ("high", "critical")


def test_long_text_is_marked_truncated():
    reply = handle({"text": "а" * (MAX_LEN + 1)})
    assert bot_core.TRUNCATED in reply.text


# --- служебные сообщения ---------------------------------------------------

@pytest.mark.parametrize("text", ["Начать", "привет!", " ПОМОЩЬ ", "/start", "/help"])
def test_greeting_words(text):
    assert classify({"text": text}) == "start"
    assert handle({"text": text}).text == bot_core.GREETING


def test_start_button_payload():
    assert classify({"text": "Начать", "payload": '{"command":"start"}'}) == "start"
    assert classify({"text": "", "payload": {"command": "start"}}) == "start"


def test_helped():
    reply = handle({"text": "Помогло!"})
    assert (reply.event, reply.text) == ("helped", bot_core.THANKS)


@pytest.mark.parametrize(
    "msg",
    [
        {"text": "привет, это мошенники?"},
        {"text": "помогло", "fwd_messages": [{"text": SCAM}]},
        {"text": "привет", "reply_message": {"text": SCAM}},
    ],
)
def test_service_words_with_content_are_checked(msg):
    assert classify(msg) == "check"


def test_photo_without_text_gets_copy_instructions():
    msg = {"text": "", "attachments": [{"type": "photo", "photo": {}}]}
    reply = handle(msg)
    assert (reply.event, reply.text) == ("image", bot_core.IMAGE_HELP)


def test_forwarded_photo_without_text_gets_copy_instructions():
    msg = {"text": "", "fwd_messages": [{"text": "", "attachments": [{"type": "photo"}]}]}
    assert handle(msg).event == "image"


@pytest.mark.parametrize("msg", [{"text": ""}, {"text": "  ", "attachments": [{"type": "sticker"}]}])
def test_empty_input_asks_for_text(msg):
    reply = handle(msg)
    assert (reply.event, reply.text) == ("empty", bot_core.ASK_TEXT)


# --- формат ответа ---------------------------------------------------------

@pytest.mark.parametrize(
    "text, first_line",
    [
        ("Ваш аккаунт заблокирован", "🟠 Есть настораживающие признаки"),
        ("Вы выиграли приз", "🔴 Похоже на мошенников"),
        (SCAM, "🔴 Похоже на мошенников"),
        ("Привет, как дела?", "🟢 Явных признаков мошенничества не найдено"),
    ],
)
def test_first_line_by_level(text, first_line):
    assert format_reply(analyze(text)).splitlines()[0] == first_line


def test_red_reply_lists_top3_signs_action_and_feedback():
    result = analyze(SCAM)
    lines = format_reply(result).splitlines()
    strong = [s for s in result["signs"] if s["score"] >= 10][:3]
    assert lines[1:4] == [f"{s['icon']} {s['title']}" for s in strong]
    assert result["recommendations"][0] in lines
    assert bot_core.ASK_FEEDBACK in lines
    assert lines[-1] == bot_core.DISCLAIMER


def test_green_reply_has_no_signs_and_fixed_action():
    result = analyze("Напишите мне в телеграм")  # low, но есть признак со score 15
    assert result["level"] == "low" and result["signs"]
    lines = format_reply(result).splitlines()
    assert lines == [bot_core.VERDICTS["low"], "", bot_core.LOW_ACTION, bot_core.DISCLAIMER]


def test_neutral_link_sign_never_shown():
    result = analyze("Ваш аккаунт заблокирован https://example.com")
    assert any(s["score"] == 5 for s in result["signs"])
    assert "В сообщении есть ссылка" not in format_reply(result)


def test_reply_has_no_technical_link_details():
    result = analyze("Ваш приз тут http://xn--80ak6aa92e.xyz")
    reply = format_reply(result)
    for jargon in ("punycode", "xn--", ".xyz", "Доменная зона"):
        assert jargon not in reply


# --- ошибки ----------------------------------------------------------------

def test_analyze_failure_returns_fallback(monkeypatch):
    def boom(text):
        raise RuntimeError(text)

    monkeypatch.setattr(bot_core, "analyze", boom)
    reply = handle({"text": SCAM})
    assert (reply.event, reply.text) == ("error", bot_core.FAILED)
