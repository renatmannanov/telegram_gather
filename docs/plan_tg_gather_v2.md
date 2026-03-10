# tg_gather v2 — коннектор Telegram → ayda_think

*Март 2026. Заменяет plan_tg_gather.md.*
*Связанный план: plan_ayda_think_v2.md*

---

## Роль в системе

tg_gather — коннектор. Собирает данные из Telegram (saved messages, личный канал) и пишет их напрямую в PostgreSQL ayda_think. Не обрабатывает, не анализирует — только собирает.

```
tg_gather (Telethon userbot, Railway)
│
├── handlers/voice_handler.py     ← как было (транскрипция)
├── assistant/                    ← как было (сводки чатов)
│
└── fragments/                    ← НОВОЕ
    └── collector.py              # Сбор saved + канал → INSERT в PostgreSQL
```

tg_gather **не** генерит эмбеддинги, **не** кластеризует. Только INSERT сырых данных. Всю обработку делает ayda_think.

---

## Почему отдельный процесс

Telegram бот (python-telegram-bot) и Telethon userbot — разные API:
- Бот получает только то, что ему пишут
- Telethon читает всё: saved messages, каналы, подписки, переписки
- Разные библиотеки, разная авторизация (бот-токен vs телефон+сессия)

Объединить нельзя без проблем. Поэтому tg_gather остаётся отдельным процессом на Railway, но подключённым к **той же PostgreSQL**, что и ayda_think.

---

## Текущее состояние tg_gather

Что уже работает:
- Telethon userbot на Railway
- Транскрипция голосовых (OpenAI Whisper + GPT-4o-mini)
- Сводки чатов (assistant модуль)
- Health monitoring
- Деплой через Docker на Railway

Чего нет:
- Сбор saved messages / каналов
- Запись в PostgreSQL (сейчас нет БД вообще, только JSON-файлы)

---

## Зоны ответственности: кто что создаёт

| Объект | Кто создаёт | Почему |
|--------|------------|--------|
| Таблица `fragments` | **ayda_think** (миграции) | ayda_think — владелец схемы, он же обрабатывает данные |
| Таблица `gather_state` | **tg_gather** (при старте) | Это внутреннее состояние gather'а, ayda_think о нём не знает |
| Расширение pgvector | **ayda_think** (миграции) | tg_gather не пишет эмбеддинги, ему pgvector не нужен |

**Важно:** tg_gather **зависит** от того, что ayda_think уже создал таблицу `fragments`. Порядок деплоя: сначала ayda_think (создаст таблицу), потом tg_gather (начнёт INSERT).

---

## Этап 0 — Восстановление сессии (блокер)

Telethon-сессия на Railway может быть протухшей. Без рабочей сессии ничего не заработает.

1. Локально: `python main.py` → авторизоваться по QR/коду
2. Закодировать сессию: `base64 -w0 telegram_gather.session`
3. Обновить `TELEGRAM_SESSION_BASE64` на Railway
4. Проверить: сервис стартует без ошибок авторизации

**Это нужно сделать первым. Всё остальное зависит от рабочей сессии.**

---

## Что меняется

### 1. Подключение к PostgreSQL ayda_think

tg_gather подключается к **той же** PostgreSQL, что и ayda_think. На Railway оба сервиса в одном проекте → внутренняя сеть.

Новая env-переменная:
```
DATABASE_URL=postgresql://user:pass@postgres.railway.internal:5432/railway
```

Зависимости (добавить в requirements.txt):
```
asyncpg>=0.29.0
```

**Почему asyncpg, а не psycopg2 + SQLAlchemy:**
- Весь tg_gather на asyncio/Telethon. Синхронный psycopg2 блокирует event loop на каждом INSERT.
- Для простых INSERT-ов asyncpg напрямую достаточно, ORM не нужен.
- `asyncpg.create_pool()` из коробки даёт reconnect при перезапуске PostgreSQL на Railway.

### 2. Модуль fragments/

```
telegram-gather/
├── fragments/
│   ├── __init__.py
│   ├── collector.py       # FragmentCollector: читает сообщения через Telethon
│   └── db.py              # INSERT в таблицу fragments (asyncpg)
```

### 3. fragments/db.py — async + connection pool

```python
import asyncpg
import json
import logging

class FragmentsDB:
    def __init__(self):
        self.pool = None

    async def connect(self, database_url: str):
        """Создаёт connection pool с автоматическим reconnect."""
        self.pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=3
        )
        # Создать gather_state если не существует
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS gather_state (
                    source VARCHAR(100) PRIMARY KEY,
                    last_msg_id BIGINT,
                    last_collected_at TIMESTAMP DEFAULT NOW()
                )
            """)

    async def insert_fragment(self, external_id, source, text_content,
                              created_at, tags, content_type, metadata) -> bool:
        """INSERT фрагмента. Возвращает True если вставлен, False если дубликат.

        tags передаётся как list[str] → PostgreSQL TEXT[].
        asyncpg конвертирует list[str] в TEXT[] автоматически.
        metadata передаётся как JSON-строка → PostgreSQL JSONB.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                INSERT INTO fragments (external_id, source, text, created_at,
                                       tags, content_type, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (external_id) DO NOTHING
            """, external_id, source, text_content, created_at,
                tags, content_type, json.dumps(metadata))
            # result = 'INSERT 0 1' или 'INSERT 0 0'
            return result == 'INSERT 0 1'

    async def get_last_id(self, source: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_msg_id FROM gather_state WHERE source = $1",
                source
            )
            return row['last_msg_id'] if row else 0

    async def save_last_id(self, source: str, msg_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO gather_state (source, last_msg_id, last_collected_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (source) DO UPDATE SET
                    last_msg_id = $2,
                    last_collected_at = NOW()
            """, source, msg_id)

    async def close(self):
        if self.pool:
            await self.pool.close()
```

### 4. fragments/collector.py

```python
import logging
import re

URL_PATTERN = re.compile(r'https?://\S+')

class FragmentCollector:
    """Собирает сообщения из Telegram и пишет в PostgreSQL."""

    def __init__(self, client, db):
        self.client = client  # TelegramClient
        self.db = db          # FragmentsDB

    async def collect_new(self, sources: list[str]) -> dict:
        """Собирает новые сообщения. Возвращает статистику."""
        stats = {'inserted': 0, 'skipped': 0}

        for source in sources:
            last_id = await self.db.get_last_id(source)
            max_id = last_id

            async for msg in self.client.iter_messages(
                source, min_id=last_id, reverse=True
            ):
                if not msg.text or len(msg.text.strip()) < 10:
                    continue

                inserted = await self.db.insert_fragment(
                    external_id=f"telegram_{source}_{msg.id}",
                    source='telegram',
                    text_content=msg.text,
                    created_at=msg.date,
                    tags=self._extract_tags(msg.text),
                    content_type=self._detect_type(msg),
                    metadata={
                        'telegram_msg_id': msg.id,
                        'chat': str(source),
                        'is_forward': msg.forward is not None
                    }
                )
                if inserted:
                    stats['inserted'] += 1
                else:
                    stats['skipped'] += 1

                max_id = max(max_id, msg.id)

            if max_id > last_id:
                await self.db.save_last_id(source, max_id)

        return stats

    def _extract_tags(self, text: str) -> list[str]:
        return [w for w in text.split() if w.startswith('#')]

    def _detect_type(self, msg) -> str:
        if msg.forward is not None:
            return 'repost'
        if URL_PATTERN.search(msg.text):
            return 'link'
        return 'note'
```

### 5. Реалтайм-сбор (event handler) + polling для истории

Вместо "раз в 24 часа" — два режима:

```python
# В main.py:

from fragments.collector import FragmentCollector
from fragments.db import FragmentsDB

# Инициализация
fragments_db = FragmentsDB()
await fragments_db.connect(os.getenv('DATABASE_URL'))
collector = FragmentCollector(client, fragments_db)

# --- Режим 1: Реалтайм ---
# Event handler на новые сообщения в saved messages
from telethon import events

@client.on(events.NewMessage(chats='me'))
async def on_saved_message(event):
    """Моментально сохраняет новые сообщения в saved."""
    msg = event.message
    if not msg.text or len(msg.text.strip()) < 10:
        return
    result = await collector.db.insert_fragment(
        external_id=f"telegram_me_{msg.id}",
        source='telegram',
        text_content=msg.text,
        created_at=msg.date,
        tags=collector._extract_tags(msg.text),
        content_type=collector._detect_type(msg),
        metadata={
            'telegram_msg_id': msg.id,
            'chat': 'me',
            'is_forward': msg.forward is not None
        }
    )
    if result:
        # Обновляем last_id чтобы bulk_collect знал где остановиться
        await collector.db.save_last_id('me', msg.id)
        logging.info(f"Fragment saved (realtime): me_{msg.id}")

# --- Режим 2: Polling для каналов ---
# Каналы не всегда шлют events, поэтому polling раз в час
async def channel_polling_loop():
    # 'me' исключён — для saved работает реалтайм event handler.
    # Polling только для каналов, где events могут не приходить.
    all_sources = parse_sources(os.getenv('GATHER_SOURCES', ''))
    sources = [s for s in all_sources if s != 'me']
    if not sources:
        logging.info("No channel sources configured, polling disabled")
        return
    while True:
        try:
            stats = await collector.collect_new(sources)
            if stats['inserted']:
                logging.info(f"Channel polling: {stats}")
        except Exception as e:
            logging.error(f"Channel polling error: {e}")
        await asyncio.sleep(3600)  # раз в час

asyncio.create_task(channel_polling_loop())
```

### 6. Конфигурация источников

Источники из env-переменной, не хардкод:

```
# .env / Railway variables
GATHER_SOURCES=me,my_channel_username
# или по ID:
GATHER_SOURCES=me,-1001234567890
```

`'me'` — всегда saved messages (Telethon convention).
Остальные — username или numeric ID канала.

**Парсинг:** если строка — число (в т.ч. отрицательное), конвертить в `int`. Иначе Telethon не найдёт канал по строке `"-1001234567890"`.

```python
def parse_sources(env_value: str) -> list:
    sources = []
    for s in env_value.split(','):
        s = s.strip()
        if not s:
            continue
        try:
            sources.append(int(s))  # numeric ID (отрицательные числа для каналов)
        except ValueError:
            sources.append(s)       # username строкой
    return sources
```

---

## Состояние сбора

Таблица `gather_state` в PostgreSQL (создаётся при старте tg_gather):

```sql
CREATE TABLE IF NOT EXISTS gather_state (
    source VARCHAR(100) PRIMARY KEY,
    last_msg_id BIGINT,
    last_collected_at TIMESTAMP DEFAULT NOW()
);
```

---

## Что собираем

### Источники

| Источник | Telethon entity | Что там |
|----------|----------------|---------|
| Saved messages | `'me'` | Сохранёнки из каналов, свои заметки |
| Личный канал | username или ID из `GATHER_SOURCES` | Заметки, ссылки, мысли |

### Что берём

- Текстовые сообщения длиной > 10 символов
- Текст из подписей к медиа (если есть)
- Forward-информация (откуда переслано)

### Что НЕ берём

- Сообщения короче 10 символов ("ок", "да")
- Медиа без текста (фото, видео, стикеры)
- Сервисные сообщения (join/leave/pin)

### Определение типа контента

| content_type | Как определяем |
|-------------|---------------|
| `note` | Оригинальное сообщение без ссылок |
| `link` | Содержит URL (regex `https?://\S+`) |
| `repost` | `msg.forward is not None` |

Тип `quote` убран — ненадёжное определение по кавычкам. Можно добавить позже через LLM-классификацию если понадобится.

---

## Первичный сбор (bulk import)

Отдельный скрипт, **не в main.py**. Можно переиспользовать существующий `fetch_chat.py`.

```python
# scripts/bulk_collect.py (или расширение fetch_chat.py)

async def bulk_collect(client, db, sources, batch_size=100):
    """Первичный сбор всей истории. Запускается один раз."""
    for source in sources:
        count = 0
        async for msg in client.iter_messages(source, reverse=True):
            if not msg.text or len(msg.text.strip()) < 10:
                continue
            await db.insert_fragment(...)
            count += 1
            if count % batch_size == 0:
                logging.info(f"[{source}] Collected {count} fragments...")
        logging.info(f"[{source}] Done: {count} total fragments")
```

Запуск:
```bash
python scripts/bulk_collect.py --sources me my_channel
```

---

## Деплой на Railway

### Текущая схема (одна БД на двоих)

```
Railway Project
│
├── PostgreSQL + pgvector
│       ↑               ↑
├── tg_gather           │
│   (INSERT fragments)  │
│                       │
└── ayda_think ─────────┘
    (SELECT + обработка)
```

### Что нужно сделать на Railway

1. Убедиться что tg_gather и ayda_think в **одном Railway проекте**
2. Добавить tg_gather переменную `DATABASE_URL` → тот же PostgreSQL (internal URL)
3. Обновить Dockerfile (добавить asyncpg)
4. **Порядок деплоя:** сначала ayda_think (создаст таблицу `fragments`), потом tg_gather

---

## Порядок реализации

### Этап 0 — Восстановление сессии (блокер)
- [ ] Локально: запустить main.py, авторизоваться
- [ ] Закодировать сессию в base64
- [ ] Обновить TELEGRAM_SESSION_BASE64 на Railway
- [ ] Проверить: сервис стартует без ошибок авторизации

### Этап 1 — Подключение к PostgreSQL
- [ ] Добавить asyncpg в requirements.txt
- [ ] fragments/db.py: FragmentsDB с connection pool
- [ ] Создание gather_state при подключении
- [ ] Тест: подключиться к PostgreSQL ayda_think, INSERT одного фрагмента
- [ ] Настроить DATABASE_URL на Railway (internal URL)

### Этап 2 — Collector + реалтайм для saved
- [ ] fragments/collector.py: FragmentCollector
- [ ] Event handler на новые сообщения в 'me' (реалтайм)
- [ ] Определение content_type (note / link / repost)
- [ ] Извлечение тегов (#hashtags)
- [ ] Статистика: inserted vs skipped (для логов)
- [ ] Тест: сохранить сообщение в saved → проверить что попало в БД

### Этап 3 — Polling для каналов
- [ ] Конфиг: GATHER_SOURCES из env-переменной
- [ ] Polling loop для каналов (раз в час)
- [ ] gather_state: сохранение/чтение last_id
- [ ] Тест: добавить канал, дождаться polling, проверить данные

### Этап 4 — Первичный сбор (bulk)
- [ ] scripts/bulk_collect.py (или расширение fetch_chat.py)
- [ ] Пачками с логированием прогресса
- [ ] Запустить: собрать всю историю saved + канал
- [ ] Проверить: сколько фрагментов, нет ли дублей

### Этап 5 — Деплой
- [ ] Обновить Dockerfile
- [ ] Добавить DATABASE_URL на Railway
- [ ] Проверить что tg_gather и ayda_think видят одну PostgreSQL
- [ ] Smoke test на Railway

---

## Примерные объёмы

| Источник | Сообщений | Размер |
|----------|-----------|--------|
| Saved messages | 1000-3000 | ~500 КБ - 1.5 МБ |
| Личный канал | ~600 | ~200-300 КБ |
| **Итого** | **~2000-4000** | **~1-2 МБ** |

INSERT 4000 записей в PostgreSQL — секунды. Узкое место — Telethon rate limits при первичном сборе (может занять 5-15 минут).

---

## Что НЕ меняется

- handlers/voice_handler.py — без изменений
- assistant/ — без изменений
- services/ — без изменений
- config.py — +1 переменная (DATABASE_URL)
- main.py — +15 строк (import + db init + event handler + polling loop)

---

*Документ создан: март 2026*
*Заменяет: plan_tg_gather.md*
