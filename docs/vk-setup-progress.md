# Настройка VK-бота: где остановились

Сохранено 2026-10-04. Полная инструкция — README, раздел «Бот в сообщениях VK-сообщества».

## Что уже есть

- Код бота влит в `main` (PR #1). Сервис на Render: `shchit-ot-moshennikov`, статус Deployed.
- Адрес сервиса: https://shchit-ot-moshennikov.onrender.com
- VK → Управление → Работа с API → Callback API: сервер «Сервер 1» создан, версия API 5.199.
- Строка подтверждения из VK: `00e6f53a`.
- «Настройки для бота» в VK не нашлись — это не обязательно, бот работает и без кнопки «Начать».

## Что осталось

- [ ] **VK, Callback API:** заменить секретный ключ на случайную строку (20–30 букв и цифр, не личный пароль) и нажать «Сохранить».
- [ ] **VK, Ключи доступа:** создать ключ с правом «Сообщения сообщества». Никому не присылать.
- [ ] **Render → сервис shchit-ot-moshennikov → Environment** (не Environment Group!): добавить
  - `VK_CONFIRMATION` = `00e6f53a`
  - `VK_SECRET` = секретный ключ из первого пункта
  - `VK_GROUP_TOKEN` = ключ доступа

  затем нажать «Save, rebuild, and deploy».
- [ ] **Render → Settings → Start Command:** должно быть `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`.
- [ ] Открыть https://shchit-ot-moshennikov.onrender.com/api/health — ждём `"vk":"ok"`.
  - `"error"` — неверный ключ доступа или нет права на сообщения;
  - `"disabled"` — Render не видит `VK_GROUP_TOKEN`;
  - нет поля `vk` — работает старая версия, нужно развернуть заново.
- [ ] **VK, Callback API:** Адрес = `https://shchit-ot-moshennikov.onrender.com/vk/callback` → «Подтвердить».
- [ ] **VK, Типы событий:** отметить только «Входящее сообщение».
- [ ] С другого аккаунта написать сообществу «привет», затем подозрительное сообщение.

Когда вернётесь к настройке в Claude Code, скажите: «продолжим настройку VK-бота, см. docs/vk-setup-progress.md».
