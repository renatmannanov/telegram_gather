# Шаг 0: Миграция в ayda_think — добавить колонки

> Зависит от: нет
> Статус: pending

## Задача

Добавить три колонки в таблицу `fragments` через ayda_think (владелец схемы).

## Что делать

### 1. Модель SQLAlchemy

Файл: `c:\Users\renat\projects\03_ayda_think\storage\fragments_db.py`

Добавить в класс `Fragment`:

```python
sender_id           = Column(BigInteger, nullable=True)      # Telegram user ID
channel_id          = Column(BigInteger, nullable=True)      # Telegram chat ID (-100 format)
message_thread_id   = Column(BigInteger, nullable=True)      # Forum topic ID (1=General)
```

### 2. ALTER TABLE патч в init_db()

Файл: `c:\Users\renat\projects\03_ayda_think\storage\db.py`, функция `init_db()`

Добавить идемпотентный патч (после существующих):

```sql
ALTER TABLE fragments
    ADD COLUMN IF NOT EXISTS sender_id BIGINT,
    ADD COLUMN IF NOT EXISTS channel_id BIGINT,
    ADD COLUMN IF NOT EXISTS message_thread_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_fragments_channel_id ON fragments (channel_id);
CREATE INDEX IF NOT EXISTS idx_fragments_sender_id ON fragments (sender_id);
CREATE INDEX IF NOT EXISTS idx_fragments_channel_thread ON fragments (channel_id, message_thread_id);
```

Индекс на channel_id — для быстрой фильтрации по каналу.
Индекс на sender_id — для фильтрации по автору.
Составной индекс (channel_id, message_thread_id) — для фильтрации `?topic_id=N` внутри канала (step_4).

### 3. Деплой

- Коммит в ayda_think
- Деплой на Railway (или перезапуск — init_db() сработает при старте)
- Проверить что колонки появились

## Критерии готовности

- [ ] `\d fragments` показывает sender_id BIGINT, channel_id BIGINT, message_thread_id BIGINT
- [ ] Индексы созданы: idx_fragments_channel_id, idx_fragments_sender_id, idx_fragments_channel_thread
- [ ] Существующие данные не затронуты (NULL в новых колонках)
- [ ] ayda_think стартует без ошибок
