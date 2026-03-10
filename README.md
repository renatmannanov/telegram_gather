# Telegram Gather

Персональный Telegram-ассистент (userbot), который автоматически транскрибирует голосовые сообщения в приватных чатах.

## Возможности

- Автоматическая транскрипция голосовых сообщений и аудиофайлов
- Поддержка форматов: `.ogg`, `.mp3`, `.wav`, `.m4a`
- Улучшение текста с помощью GPT-4o-mini (удаление слов-паразитов, исправление пунктуации)
- Работает в приватных чатах

## Требования

- Python 3.10+
- Telegram API credentials (получить на https://my.telegram.org)
- OpenAI API key (получить на https://platform.openai.com/api-keys)

## Установка

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd telegram-gather
```

### 2. Создать виртуальное окружение

**Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

Скопировать `.env.example` в `.env` и заполнить:

```bash
cp .env.example .env
```

Обязательные переменные:
- `TELEGRAM_API_ID` - ID приложения из my.telegram.org
- `TELEGRAM_API_HASH` - Hash приложения из my.telegram.org
- `TELEGRAM_PHONE` - Номер телефона в формате +79001234567
- `OPENAI_API_KEY` - API ключ OpenAI

Опциональные:
- `TRANSCRIPTION_LANGUAGE` - Язык транскрипции (по умолчанию: `ru`)
- `IMPROVE_TRANSCRIPTION` - Улучшать текст через GPT (по умолчанию: `true`)
- `SESSION_NAME` - Имя файла сессии (по умолчанию: `telegram_gather`)

## Запуск

```bash
python main.py
```

При первом запуске:
1. Введите код подтверждения из Telegram
2. Если включена 2FA, введите пароль

После авторизации бот начнет работать. Все голосовые сообщения в приватных чатах будут автоматически транскрибироваться.

## Структура проекта

```
telegram-gather/
├── main.py                 # Точка входа
├── config.py               # Загрузка конфигурации
├── requirements.txt        # Зависимости
├── handlers/
│   └── voice_handler.py    # Обработчик голосовых сообщений
└── services/
    └── transcription_service.py  # Whisper + GPT интеграция
```

## Чтение чатов через Claude Code

Скрипт `fetch_chat.py` позволяет Claude Code подключаться к Telegram и выгружать сообщения из любых чатов для анализа.

### Как использовать

```bash
# Выгрузить сообщения из одного или нескольких чатов
python fetch_chat.py "Название чата" --period 1w
python fetch_chat.py "Чат 1" "Чат 2" --period 2w

# Опции
#   -p, --period    Период: 12h, 1d, 3d, 1w, 2w (по умолчанию: 1w)
#   -f, --format    Формат: text или json (по умолчанию: text)
#   -o, --output    Папка для файлов (по умолчанию: data/exports)
#   -l, --limit     Макс. сообщений на чат (по умолчанию: 200)
```

Файлы сохраняются в `data/exports/` — потом их можно прочитать через Read tool.

### Поиск чатов по ключевому слову

Если не знаешь точное название чата, можно найти все чаты по ключевым словам. Пример одноразового скрипта:

```python
import asyncio, sys, io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from telethon import TelegramClient
from config import config

async def main():
    client = TelegramClient(config["session_name"], config["api_id"], config["api_hash"])
    await client.connect()
    async for d in client.iter_dialogs():
        if any(kw in (d.title or "").lower() for kw in ["ключевое", "слово"]):
            print(f"  ID: {d.id}  |  {d.title}  |  {type(d.entity).__name__}")
    await client.disconnect()

asyncio.run(main())
```

### Важно

- Скрипт использует существующую Telethon-сессию (`telegram_gather.session`). Если сессия не авторизована — сначала запусти `python main.py`.
- Скрипт **не изменяет** `assistant_state.json` и не влияет на работу бота.
- Название чата должно совпадать с тем, что видно в Telegram (регистр не важен).
- Папка `data/` в `.gitignore` — экспорты не попадут в git.

## Лицензия

MIT
