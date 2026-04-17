# Шаг 3: Realtime listener + collector — sender_id и channel_id

> Зависит от: шаг 1
> Статус: pending

## Задача

Обновить event handler в `main.py` и методы в `collector.py` чтобы передавали sender_id и channel_id.

## Что делать

### 1. main.py — on_new_fragment()

Строки ~204-218. Добавить sender_id и channel_id:

```python
result = await fragment_collector.db.insert_fragment(
    external_id=f"telegram_{source_key}_{msg.id}",
    source='telegram',
    text_content=msg.text,
    created_at=msg.date,
    tags=fragment_collector._extract_tags(msg.text),
    content_type=fragment_collector._detect_type(msg),
    metadata={
        'telegram_msg_id': msg.id,
        'chat': source_key,
        'is_forward': msg.forward is not None
    },
    sender_id=msg.sender_id,
    channel_id=event.chat_id if source_key != 'me' else None,
)
```

`event.chat_id` — уже int в -100 формате, кастить не нужно.
Для `source_key='me'` (saved messages) — channel_id=None.

### 2. fragments/collector.py — collect_new() и bulk_collect()

В обоих методах при вызове `db.insert_fragment()` добавить:

```python
sender_id=msg.sender_id,
channel_id=int(source_key),  # source_key — строка, колонка BIGINT
```

`source_key` — это `str(dialog.id)`, числовой в -100 формате, но строка. asyncpg не кастит строку в BIGINT автоматически, поэтому `int()` обязателен.

Для `source_key='me'` — передавать `channel_id=None` (saved messages не канал):
```python
channel_id=int(source_key) if source_key != 'me' else None,
```

## Что НЕ делать

- Не рефакторить существующую логику
- Не менять формат external_id
- Не трогать gather_state
- message_thread_id — отдельный шаг 4

## Критерии готовности

- [ ] Realtime handler заполняет sender_id и channel_id
- [ ] collect_new() заполняет sender_id и channel_id
- [ ] bulk_collect() заполняет sender_id и channel_id
