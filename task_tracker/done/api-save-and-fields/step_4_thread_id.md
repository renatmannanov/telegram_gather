# Шаг 4: message_thread_id — поддержка форум-топиков

> Зависит от: шаг 1
> Статус: pending

## Задача

Извлекать topic ID из сообщений в форум-группах и передавать в insert_fragment().
Добавить message_thread_id в ответ API `/api/messages`.

## Алгоритм извлечения topic_id

На уровне MTProto нет поля `message_thread_id` на Message.
Информация лежит в `message.reply_to` (тип `MessageReplyHeader`).

### Таблица поведения

| Сценарий | reply_to | reply_to_msg_id | reply_to_top_id | forum_topic |
|---|---|---|---|---|
| General topic, обычное | None | — | — | — |
| General topic, реплай на X | есть | X | thread root / None | False |
| Именованный топик (id=T), обычное | есть | T (= topic_id!) | None | True |
| Именованный топик (id=T), реплай на X | есть | X | T (= topic_id) | True |
| Обычная группа, обычное | None | — | — | — |
| Обычная группа, реплай на X | есть | X | thread root / None | False |

### Функция

```python
from telethon.tl.types import MessageReplyHeader

def get_topic_id(message, chat=None):
    """
    Возвращает topic ID для сообщения в форум-группе.
    - Именованный топик: ID сервисного сообщения (например 3, 15)
    - General topic: 1
    - Обычная группа / не форум: None
    
    chat — entity чата (нужен для определения General topic).
    Если не передан, General topic вернёт None.
    """
    reply = message.reply_to
    
    if isinstance(reply, MessageReplyHeader) and reply.forum_topic:
        # Именованный топик
        if reply.reply_to_top_id is not None:
            return reply.reply_to_top_id  # реплай внутри топика
        else:
            return reply.reply_to_msg_id  # обычное сообщение в топике
    
    # Не именованный топик — может быть General или не форум
    if chat is not None and getattr(chat, 'forum', False):
        return 1  # General topic
    
    return None
```

### Где разместить

Создать утилиту или добавить как метод в collector. Рекомендую: отдельная функция в `fragments/utils.py` (или прямо в `collector.py`).

## Что делать

### 1. Realtime handler (main.py)

```python
chat_entity = await event.get_chat()
thread_id = get_topic_id(msg, chat=chat_entity)

await fragment_collector.db.insert_fragment(
    ...,
    message_thread_id=thread_id,
)
```

### 2. collector.py — collect_new() и bulk_collect()

```python
# Получить entity один раз до цикла для определения forum-флага
chat_entity = await self.client.get_entity(source)
is_forum = getattr(chat_entity, 'forum', False)

# В цикле — передавать chat только если форум (иначе get_topic_id вернёт None без доп. логики)
for msg in messages:
    thread_id = get_topic_id(msg, chat=chat_entity) if is_forum else None
    await self.db.insert_fragment(
        ...,
        message_thread_id=thread_id,
    )
```

**Важно**: `get_entity()` — один API-вызов на source, не на сообщение. Для не-форумов `is_forum=False` — `get_topic_id` даже не вызывается, thread_id сразу None.

### 3. API ответ (api.py / fetch_chat.py)

Добавить `message_thread_id` в dict возвращаемый `fetch_messages()`:

```python
# fetch_chat.py, в цикле формирования messages:
"message_thread_id": get_topic_id(msg, chat=entity),
```

И в API save (step_2) — передавать в insert_fragment:
```python
message_thread_id=msg_data.get('message_thread_id'),
```

### 4. Опциональный параметр ?topic_id=N

В `handle_messages()` (api.py):

```python
topic_id = request.query.get("topic_id")
if topic_id is not None:
    topic_id = int(topic_id)
    messages = [m for m in messages if m.get("message_thread_id") == topic_id]
```

## Важно

- `get_chat()` / `get_entity()` — доп. API вызов. В realtime `event.get_chat()` закеширован. В collector `get_entity()` нужно вызвать 1 раз до цикла
- Для обычных групп (не форумов) message_thread_id будет NULL — это ок
- Для `source='me'` (saved messages) — тоже NULL

## Критерии готовности

- [ ] Сообщения из именованного топика → message_thread_id = topic_id
- [ ] Сообщения из General topic → message_thread_id = 1
- [ ] Сообщения из обычной группы → message_thread_id = NULL
- [ ] API ответ содержит поле message_thread_id
- [ ] `?topic_id=3` фильтрует только Bus-сообщения
