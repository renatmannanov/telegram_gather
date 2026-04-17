# Шаг 1: Обновить INSERT в db.py — sender_id, channel_id, message_thread_id

> Зависит от: шаг 0 (колонки должны существовать в БД)
> Статус: pending

## Задача

Обновить `FragmentsDB.insert_fragment()` чтобы принимал и сохранял новые поля.

## Что делать

Файл: `fragments/db.py`

1. Добавить параметры `sender_id=None, channel_id=None, message_thread_id=None`
2. Обновить INSERT запрос

Было:
```python
async def insert_fragment(self, external_id, source, text_content,
                          created_at, tags, content_type, metadata) -> bool:
    ...
    result = await conn.execute("""
        INSERT INTO fragments (external_id, source, text, created_at,
                               tags, content_type, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        ON CONFLICT (external_id) DO NOTHING
    """, external_id, source, text_content, created_at,
        tags, content_type, json.dumps(metadata))
```

Стало:
```python
async def insert_fragment(self, external_id, source, text_content,
                          created_at, tags, content_type, metadata,
                          sender_id=None, channel_id=None,
                          message_thread_id=None) -> bool:
    ...
    result = await conn.execute("""
        INSERT INTO fragments (external_id, source, text, created_at,
                               tags, content_type, metadata,
                               sender_id, channel_id, message_thread_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
        ON CONFLICT (external_id) DO NOTHING
    """, external_id, source, text_content, created_at,
        tags, content_type, json.dumps(metadata),
        sender_id, channel_id, message_thread_id)
```

## Важно

- Дефолты `=None` — существующие вызовы не ломаются
- Типы: `sender_id` int, `channel_id` int, `message_thread_id` int
- ON CONFLICT не затрагивается

## Критерии готовности

- [ ] INSERT с новыми параметрами — работает
- [ ] INSERT без новых параметров — работает (backward compatible)
- [ ] ON CONFLICT не ломается
