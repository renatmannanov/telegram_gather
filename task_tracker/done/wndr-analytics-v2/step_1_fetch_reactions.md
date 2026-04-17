# Шаг 1: Добавить реакции в fetch_topic.py + пересобрать топики

> Зависит от: нет
> Статус: [ ] pending

## Задача

Изменить `fetch_topic.py`: при сборе каждого сообщения извлекать реакции из `msg.reactions`.

Структура `msg.reactions` в Telethon 1.42:
- `msg.reactions` → `MessageReactions` или `None`
- `msg.reactions.results` → список `ReactionCount`
- каждый `ReactionCount` имеет `.reaction` (ReactionEmoji с `.emoticon`) и `.count`

Добавить в каждое сообщение поле:
```json
"reactions": [{"emoji": "❤️", "count": 3}, {"emoji": "👍", "count": 1}]
```
Если реакций нет — пустой список `[]`.

Также добавить поле `char_count` (длина текста) — нужно для эвристики в шаге 2.

## Изменения в коде

**`fetch_topic.py` → функция `fetch_topic_messages`:**

```python
def extract_reactions(msg) -> list:
    if not msg.reactions:
        return []
    result = []
    for rc in msg.reactions.results:
        reaction = rc.reaction
        emoji = getattr(reaction, 'emoticon', None) or getattr(reaction, 'document_id', '?')
        result.append({"emoji": str(emoji), "count": rc.count})
    return result
```

В словарь сообщения добавить:
```python
"reactions": extract_reactions(msg),
"char_count": len(msg.text or msg.message or ""),
```

## Команды для верификации

```bash
# Пересобрать один маленький топик и проверить структуру
python fetch_topic.py "WNDR chat" --topic-id 70 --name announcements -o data/exports/wndr

# Проверить что reactions появились
python -c "
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.loads(open('data/exports/wndr/wndr_topic_announcements.json', encoding='utf-8').read())
msgs = [t['root'] for t in d['threads'] if t.get('root')]
with_reactions = [m for m in msgs if m.get('reactions')]
print(f'Messages with reactions: {len(with_reactions)} / {len(msgs)}')
if with_reactions:
    print('Example:', with_reactions[0]['reactions'])
"
```

## Пересборка всех топиков (после проверки)

Запускать по одному с паузой 30-60 сек между ними:
```bash
python fetch_topic.py "WNDR chat" --topic-id 70   --name announcements -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 1    --name boltalka      -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 563  --name daily         -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 561  --name commits       -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 7073 --name harvest       -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 11002 --name together     -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 5593 --name intro         -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 2262 --name offerings     -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 68   --name requests      -o data/exports/wndr
python fetch_topic.py "WNDR chat" --topic-id 8718 --name sales         -o data/exports/wndr
```

## Критерии готовности
- [ ] В каждом сообщении есть поле `reactions` (список, может быть пустым)
- [ ] В каждом сообщении есть поле `char_count` (int)
- [ ] Все 10 топиков пересобраны
