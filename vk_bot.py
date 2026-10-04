"""
Бот в сообщениях VK-сообщества (Callback API).

VK присылает событие → сразу отвечаем "ok" → в фоне считаем ответ через
bot_core.handle() и отправляем messages.send. Дедупликация и лимит частоты
живут в памяти процесса, поэтому сервис запускается с одним воркером
(см. render.yaml).

Переменные окружения: VK_GROUP_TOKEN, VK_SECRET, VK_CONFIRMATION.
Текст сообщений не сохраняется и не попадает в логи.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse

import bot_core

API_URL = "https://api.vk.com/method/"
API_VERSION = "5.199"
SEND_TIMEOUT = 5.0
RETRY_DELAY = 1.0

CHAT_PEER_MIN = 2_000_000_000  # peer_id бесед начинаются с этого числа

DEDUP_TTL = 3600
DEDUP_MAX = 10_000
RATE_LIMIT = 10
RATE_WINDOW = 60
RATE_MAX_USERS = 10_000
RATE_LIMITED = "Слишком много сообщений, попробуйте через минуту."

log = logging.getLogger("vk_bot")
router = APIRouter()

_now = time.monotonic
_seen: OrderedDict[str, float] = OrderedDict()  # event_id -> время получения
_hits: OrderedDict[int, deque] = OrderedDict()  # from_id -> времена проверок за окно
_warned: dict[int, float] = {}  # from_id -> когда сообщили о лимите
token_status = "disabled"  # ok | error | disabled, показывается в /api/health


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _metric(event: str, level: str | None = None) -> None:
    line = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"), "channel": "vk", "event": event}
    if level:
        line["level"] = level
    print(json.dumps(line), flush=True)


def _random_id(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF


def _is_duplicate(event_id: str) -> bool:
    now = _now()
    while _seen and (now - next(iter(_seen.values())) > DEDUP_TTL or len(_seen) >= DEDUP_MAX):
        _seen.popitem(last=False)
    if event_id in _seen:
        return True
    _seen[event_id] = now
    return False


def _over_limit(user: int) -> bool:
    now = _now()
    hits = _hits.pop(user, None) or deque()
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    for other in [u for u, h in _hits.items() if not h or now - h[-1] > RATE_WINDOW]:
        del _hits[other]
        _warned.pop(other, None)
    while len(_hits) >= RATE_MAX_USERS:
        old, _ = _hits.popitem(last=False)
        _warned.pop(old, None)
    _hits[user] = hits
    if len(hits) >= RATE_LIMIT:
        return True
    hits.append(now)
    _warned.pop(user, None)
    return False


def _call(method: str, params: dict) -> dict:
    resp = httpx.post(
        API_URL + method,
        data={**params, "access_token": _env("VK_GROUP_TOKEN"), "v": API_VERSION},
        timeout=SEND_TIMEOUT,
    )
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"VK API error {body['error'].get('error_code')}")
    return body


def send(peer_id: int, text: str, random_id: int) -> bool:
    params = {"peer_id": peer_id, "message": text, "random_id": random_id}
    for attempt in range(2):
        try:
            _call("messages.send", params)
            return True
        except Exception as exc:  # noqa: BLE001 — в лог только тип ошибки, без текста
            if attempt == 0:
                time.sleep(RETRY_DELAY)
            else:
                log.warning("vk messages.send failed: %s", type(exc).__name__)
    return False


def check_token() -> str:
    """Один вызов groups.getById при старте: виден ли битый токен сразу после деплоя."""
    global token_status
    if not _env("VK_GROUP_TOKEN"):
        token_status = "disabled"
        return token_status
    try:
        _call("groups.getById", {})
        token_status = "ok"
    except Exception as exc:  # noqa: BLE001
        log.error("VK_GROUP_TOKEN check failed: %s", type(exc).__name__)
        token_status = "error"
    return token_status


def process(message: dict, key: str) -> None:
    reply = bot_core.handle(message)
    _metric(reply.event, reply.level)
    send(message["peer_id"], reply.text, _random_id(key))


def _warn_limit(peer_id: int, key: str) -> None:
    send(peer_id, RATE_LIMITED, _random_id(key + ":limit"))


@router.post("/vk/callback", include_in_schema=False)
async def vk_callback(request: Request, tasks: BackgroundTasks):
    # Тело разбираем вручную: при ошибке валидации FastAPI не должен писать его в лог.
    try:
        body = json.loads(await request.body())
    except ValueError:
        return PlainTextResponse("bad request", status_code=400)
    if not isinstance(body, dict):
        return PlainTextResponse("bad request", status_code=400)

    if body.get("type") == "confirmation":
        return PlainTextResponse(_env("VK_CONFIRMATION"))

    secret = _env("VK_SECRET")
    if not secret or not hmac.compare_digest(str(body.get("secret", "")), secret):
        return PlainTextResponse("forbidden", status_code=403)

    if body.get("type") != "message_new":
        return PlainTextResponse("ok")

    message = (body.get("object") or {}).get("message") or {}
    peer_id, user = message.get("peer_id"), message.get("from_id")
    if not isinstance(peer_id, int) or not isinstance(user, int) or peer_id >= CHAT_PEER_MIN:
        return PlainTextResponse("ok")

    key = str(body.get("event_id") or f"{peer_id}:{message.get('conversation_message_id')}")
    if _is_duplicate(key):
        return PlainTextResponse("ok")

    if _over_limit(user):
        if user not in _warned:
            _warned[user] = _now()
            tasks.add_task(_warn_limit, peer_id, key)
        return PlainTextResponse("ok")

    tasks.add_task(process, message, key)
    return PlainTextResponse("ok")
