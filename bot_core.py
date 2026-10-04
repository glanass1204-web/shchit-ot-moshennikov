"""
Ядро бота «Щит от мошенников»: что ответить на сообщение пользователя.

Не обращается к сети и не хранит текст. Принимает сообщение в формате
VK API (`text`, `payload`, `fwd_messages`, `reply_message`, `attachments`);
другой мессенджер приводит своё сообщение к этому виду.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from analyzer import MAX_LEN, analyze

GREETING = (
    "Перешлите сюда подозрительное сообщение или ссылку — я скажу, похоже ли это "
    "на мошенников. Перед отправкой уберите коды из СМС и номера карт.\n\n"
    "Переписку видят администраторы сообщества. Мы не сохраняем текст сообщений."
)
THANKS = "Спасибо! Рады, что проверка помогла."
ASK_TEXT = "Перешлите сюда текст подозрительного сообщения или ссылку."
IMAGE_HELP = (
    "Я пока не умею читать картинки. Нажмите на подозрительное сообщение "
    "и удерживайте → Копировать → вставьте текст сюда."
)
FAILED = (
    "Не получилось проверить. Пока не переводите деньги и не переходите по ссылкам — "
    "позвоните в банк по номеру на карте."
)

VERDICTS = {
    "critical": "🔴 Похоже на мошенников",
    "high": "🔴 Похоже на мошенников",
    "medium": "🟠 Есть настораживающие признаки",
    "low": "🟢 Явных признаков мошенничества не найдено",
}
LOW_ACTION = "Если сомневаетесь — позвоните отправителю по номеру, который знаете сами."
TRUNCATED = "Сообщение очень длинное, проверены первые 10 000 символов."
ASK_FEEDBACK = 'Если проверка помогла, напишите "помогло".'
DISCLAIMER = "Проверка автоматическая и не даёт 100% гарантии."

MIN_SIGN_SCORE = 10
MAX_SIGNS = 3

START_WORDS = {"начать", "привет", "помощь", "/start", "/help"}
HELPED_WORD = "помогло"


@dataclass
class Reply:
    text: str
    event: str  # check | start | helped | image | empty | error
    level: str | None = None


def _children(msg: dict) -> list[dict]:
    out = list(msg.get("fwd_messages") or [])
    if msg.get("reply_message"):
        out.append(msg["reply_message"])
    return out


def collect_text(msg: dict) -> str:
    """Текст сообщения, всех пересланных и цитируемых, плюс адреса ссылок из вложений."""
    parts: list[str] = []
    stack = [msg]
    while stack:
        m = stack.pop(0)
        if m.get("text"):
            parts.append(m["text"])
        for att in m.get("attachments") or []:
            url = (att.get("link") or {}).get("url") if att.get("type") == "link" else None
            if url:
                parts.append(url)
        stack.extend(_children(m))
    return "\n".join(parts)


def _has_photo(msg: dict) -> bool:
    stack = [msg]
    while stack:
        m = stack.pop()
        if any(a.get("type") == "photo" for a in m.get("attachments") or []):
            return True
        stack.extend(_children(m))
    return False


def _payload_command(msg: dict) -> str | None:
    payload = msg.get("payload")
    if not payload:
        return None
    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
    except ValueError:
        return None
    return data.get("command") if isinstance(data, dict) else None


def classify(msg: dict) -> str:
    """start | helped | check | image | empty."""
    if _payload_command(msg) == "start":
        return "start"
    bare = not msg.get("fwd_messages") and not msg.get("reply_message") and not msg.get("attachments")
    if bare:
        word = (msg.get("text") or "").strip().lower().rstrip(".!?,… ")
        if word in START_WORDS:
            return "start"
        if word == HELPED_WORD:
            return "helped"
    if collect_text(msg).strip():
        return "check"
    return "image" if _has_photo(msg) else "empty"


def format_reply(result: dict, truncated: bool = False) -> str:
    level = result["level"]
    lines = [VERDICTS[level]]
    if level != "low":
        signs = [s for s in result["signs"] if s["score"] >= MIN_SIGN_SCORE]
        signs.sort(key=lambda s: s["score"], reverse=True)
        lines += [f"{s['icon']} {s['title']}" for s in signs[:MAX_SIGNS]]
    lines.append("")
    lines.append(LOW_ACTION if level == "low" else result["recommendations"][0])
    if truncated:
        lines.append(TRUNCATED)
    if level != "low":
        lines.append(ASK_FEEDBACK)
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def handle(msg: dict) -> Reply:
    """Ответ на одно входящее сообщение. Никогда не бросает исключение."""
    try:
        kind = classify(msg)
        if kind == "start":
            return Reply(GREETING, "start")
        if kind == "helped":
            return Reply(THANKS, "helped")
        if kind == "image":
            return Reply(IMAGE_HELP, "image")
        if kind == "empty":
            return Reply(ASK_TEXT, "empty")
        text = collect_text(msg)
        result = analyze(text)
        return Reply(format_reply(result, truncated=len(text) > MAX_LEN), "check", result["level"])
    except Exception:  # noqa: BLE001 — пользователь всегда получает ответ
        return Reply(FAILED, "error")
