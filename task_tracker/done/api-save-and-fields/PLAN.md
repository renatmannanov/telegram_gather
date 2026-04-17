# API Save + новые поля (sender_id, channel_id, message_thread_id)

> Статус: done
> Дата: 2026-04-16 (обновлён)
> Тип: фича

## Цель

1. HTTP API `/api/messages` должен сохранять полученные сообщения в таблицу `fragments`
2. Добавить колонки `sender_id` (BIGINT), `channel_id` (BIGINT), `message_thread_id` (BIGINT) в `fragments`
3. Все коллекторы (API, realtime, bulk_collect) заполняют новые поля

## Решения

- **sender_id** — числовой Telegram user ID (`msg.sender_id`), не имя. Имя можно дёрнуть через API по ID
- **channel_id** — числовой chat ID в -100 формате (`event.chat_id`). Уже лежит в `metadata.chat`, но отдельная колонка нужна для SQL-фильтрации и индексов
- **message_thread_id** — ID топика в форум-группах. Для General topic = 1, для именованных = ID сервисного сообщения. Требует проверки `reply_to.forum_topic` + fallback на `chat.forum`
- **Миграция** — через ayda_think (владелец схемы `fragments`): добавить поля в SQLAlchemy модель + ALTER TABLE патч в `init_db()`

## Шаги

| # | Файл | Статус |
|---|------|--------|
| 0 | step_0_ayda_think_migration.md | [x] |
| 1 | step_1_db_insert.md | [x] |
| 2 | step_2_api_save.md | [x] |
| 3 | step_3_realtime_save.md | [x] |
| 4 | step_4_thread_id.md | [x] |
| 5 | step_5_completion.md | [x] |

## Порядок выполнения

1. **step_0** — миграция в ayda_think (деплой → колонки появятся в БД)
2. **step_1** — обновить insert_fragment() в telegram-gather
3. **step_2 и step_3** — параллельно: API save и realtime save
4. **step_4** — thread_id (зависит от step_1, т.к. нужен обновлённый insert)
5. **step_5** — финальная проверка

## Что НЕ трогаем

- Сессионные файлы Telethon
- assistant_config.yaml
- handlers/, services/
- Формат external_id

## Критерии готовности

- [ ] `SELECT sender_id, channel_id, message_thread_id FROM fragments LIMIT 1` — не ошибка
- [ ] `GET /api/messages?chat=neurozeh&period=1d` — сообщения возвращаются И сохраняются в БД
- [ ] `SELECT * FROM fragments WHERE channel_id = -1002163129581` — записи есть
- [ ] Realtime listener заполняет sender_id, channel_id, message_thread_id
- [ ] Для форум-группы: message_thread_id заполнен (1 для General, topic_id для именованных)
- [ ] Дубли не создаются (ON CONFLICT работает)
