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

## Лицензия

MIT
