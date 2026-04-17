# Шаг 2: API /api/messages — сохранять в БД при запросе

> Зависит от: шаг 1
> Статус: pending

## Задача

`handle_messages()` в `api.py` после fetch сообщений — сохранять их в `fragments`.

## Что делать

Файл: `api.py`

### 0. КРИТИЧНО: формат chat_id

В `api.py:83` сейчас `chat_id = getattr(entity, "id", None)` — это **голый ID** (например `2163129581`).
Realtime и collector используют `-100` формат (например `-1002163129581`).

Если не привести к единому формату — будут **разные external_id** за одно и то же сообщение → дубли.
(Именно этот баг создал 1190 дубликатов iwacado.)

**Решение**: использовать `telethon.utils.get_peer_id(entity)` — возвращает `-100` формат для каналов/групп.

```python
from telethon.utils import get_peer_id

# В handle_messages(), вместо getattr(entity, "id", None):
chat_id = get_peer_id(entity)
```

### 1. Передать db в app

В `main.py` при вызове `start_api()` — передать `fragments_db`:

```python
api_runner = await start_api(client, port=..., fragments_db=fragments_db)
```

В `api.py` функция `start_api()`:
```python
async def start_api(client, port=8080, fragments_db=None):
    ...
    app["fragments_db"] = fragments_db
```

### 2. Добавить поля в fetch_messages()

Сейчас `fetch_messages()` возвращает только dict'ы. Добавить нужные поля прямо в dict (fetch_chat.py:112-118):

```python
messages.append({
    "id": msg.id,
    "date": msg.date.strftime("%Y-%m-%dT%H:%M:%S") if msg.date else None,
    "sender": get_sender_name(msg),
    "sender_id": msg.sender_id,
    "text": msg.text or msg.message or "",
    "reply_to": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
    "is_forward": msg.forward is not None,
})
```

### 3. Сохранять сообщения после fetch

В `handle_messages()` после `fetch_messages()`:

```python
db = request.app.get("fragments_db")
if db:
    for msg_data in messages:
        text = msg_data.get('text', '')
        await db.insert_fragment(
            external_id=f"telegram_{chat_id}_{msg_data['id']}",
            source='telegram',
            text_content=text,
            created_at=datetime.fromisoformat(msg_data['date']),
            tags=[w for w in text.split() if w.startswith('#')],
            content_type='repost' if msg_data.get('is_forward') else
                         'link' if 'http' in text else 'note',
            metadata={
                'telegram_msg_id': msg_data['id'],
                'chat': str(chat_id),
                'is_forward': msg_data.get('is_forward', False),
            },
            sender_id=msg_data.get('sender_id'),
            channel_id=chat_id,
        )
```

## Важно

- Если `fragments_db` is None — API работает как раньше
- `ON CONFLICT DO NOTHING` — повторные запросы не создают дубли
- message_thread_id пока не передаём (будет в шаге 4)

## Критерии готовности

- [ ] API запрос возвращает JSON как раньше (не сломали)
- [ ] После запроса — записи в fragments с sender_id и channel_id
- [ ] Повторный запрос — дубли не создаются
- [ ] Без DATABASE_URL — API работает как раньше
