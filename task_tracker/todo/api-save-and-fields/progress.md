# Progress Log — api-save-and-fields

## Контекст для агента

- Проект: telegram-gather (c:\Users\renat\projects\telegram-gather)
- БД: PostgreSQL на Railway (asyncpg, без ORM)
- Таблица `fragments` — создана ayda_think (владелец схемы), мы только INSERT'им
- Таблица `gather_state` — создаётся в db.py connect()
- API: aiohttp, файл api.py, эндпоинт /api/messages
- Realtime: Telethon events.NewMessage в main.py
- Коллектор: fragments/collector.py — collect_new(), bulk_collect()
- Сессионные файлы Telethon — НЕ ТРОГАТЬ

## Ключевые решения (2026-04-16)

- **sender_id** — числовой Telegram user ID (BIGINT), не имя. Имя можно получить через API
- **channel_id** — числовой chat ID в -100 формате (BIGINT). Дублирует metadata.chat, но нужен для SQL-фильтрации
- **message_thread_id** — topic ID для форум-групп (BIGINT). General=1, именованные=service_msg_id
- **Миграция** — через ayda_think: модель Fragment + ALTER TABLE IF NOT EXISTS в init_db()
- **thread_id алгоритм** — НЕ использовать `getattr(message, 'reply_to_top_id')` напрямую. Нужна двухветочная логика: `reply_to.forum_topic` → именованный, `chat.forum` → General

## Ключевые файлы

- fragments/db.py:34-52 — insert_fragment() с INSERT запросом
- fragments/collector.py:37-49 — вызов insert_fragment() в collect_new()
- api.py:47-91 — handle_messages() — сюда добавить save
- main.py:204-218 — on_new_fragment() — сюда добавить новые поля
- fetch_chat.py:93-100 — get_sender_name() (для справки, не используем)
- fetch_chat.py:115 — формат dict в fetch_messages()

## Внешние зависимости

- ayda_think: c:\Users\renat\projects\03_ayda_think
  - storage/fragments_db.py — модель Fragment (добавить колонки)
  - storage/db.py — init_db() (добавить ALTER TABLE патч)

## Learnings

(заполняется в процессе работы)
