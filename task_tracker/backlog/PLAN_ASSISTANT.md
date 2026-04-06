# План: Personal Assistant для Telegram Gather

## Обзор

Добавить сервис "Персональный ассистент" к существующему Telegram userbot:
- Читать сообщения из выбранных чатов
- Создавать AI-powered summary с рекомендациями к действию
- Доставлять через отдельного Telegram бота (тот же что health alerts)

---

## Структура файлов (Feature-based)

```
telegram-gather/
├── main.py                           # [ИЗМЕНИТЬ] Добавить инициализацию ассистента
├── config.py                         # [БЕЗ ИЗМЕНЕНИЙ]
├── requirements.txt                  # [ИЗМЕНИТЬ] +pyyaml
│
├── assistant/                        # [НОВЫЙ] Весь функционал ассистента
│   ├── __init__.py                  # Экспорт: start_assistant()
│   ├── config.py                    # Загрузка YAML, dataclasses (~80 строк)
│   ├── collector.py                 # Сбор сообщений из Telethon (~100 строк)
│   ├── summarizer.py                # GPT-4o summary генерация (~120 строк)
│   ├── bot.py                       # Telegram Bot команды (~100 строк)
│   └── storage.py                   # Сохранение в файлы (~60 строк)
│
├── assistant_config.yaml             # [НОВЫЙ] Конфиг чатов и целей
│
├── handlers/                         # [БЕЗ ИЗМЕНЕНИЙ]
│   ├── __init__.py
│   └── voice_handler.py
│
├── services/                         # [БЕЗ ИЗМЕНЕНИЙ]
│   ├── __init__.py
│   ├── transcription_service.py
│   └── health_monitor.py
│
└── data/                             # [НОВЫЙ] Runtime данные
    ├── assistant_state.json         # Последние message_id по чатам
    └── summaries/
        └── 2024-01-26.md
```

### Почему feature-based:
- **Изоляция**: Весь код ассистента в одной папке `assistant/`
- **Маленькие файлы**: Каждый файл 60-120 строк, легко читать и редактировать
- **Независимость**: Можно отключить фичу удалив одну папку
- **Не ломает существующее**: handlers/ и services/ остаются как есть

---

## Файлы модуля `assistant/`

### 1. assistant/config.py (~80 строк)

```python
"""Загрузка и валидация конфигурации ассистента"""
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import yaml

@dataclass
class ChatConfig:
    display_name: str
    context: str
    priority: str = "medium"          # high | medium | low
    identifier: Optional[str] = None  # @username
    chat_id: Optional[int] = None     # или numeric ID
    keywords: List[str] = field(default_factory=list)
    max_messages: int = 100

@dataclass
class UserContext:
    name: str
    goals: List[str]
    language: str = "ru"

@dataclass
class AssistantConfig:
    user: UserContext
    chats: List[ChatConfig]
    data_dir: str = "./data"

    @classmethod
    def load(cls, path: str = "assistant_config.yaml") -> "AssistantConfig":
        """Загрузить из YAML файла"""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        user = UserContext(**data["user"])
        chats = [ChatConfig(**c) for c in data["chats"]]
        return cls(user=user, chats=chats,
                   data_dir=data.get("data_dir", "./data"))

    def get_chat(self, name: str) -> Optional[ChatConfig]:
        """Найти чат по display_name"""
        for c in self.chats:
            if c.display_name.lower() == name.lower():
                return c
        return None
```

### 2. assistant/collector.py (~100 строк)

```python
"""Сбор сообщений из Telegram чатов"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from telethon import TelegramClient

class MessageCollector:
    def __init__(self, client: TelegramClient, config: AssistantConfig):
        self.client = client
        self.config = config
        self.state_file = Path(config.data_dir) / "assistant_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"last_ids": {}}

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2))

    async def get_unread(self, chat_config: ChatConfig) -> list:
        """Получить новые сообщения с последнего запроса"""
        entity = await self._resolve_chat(chat_config)
        last_id = self._state["last_ids"].get(str(chat_config.chat_id), 0)

        messages = []
        async for msg in self.client.iter_messages(
            entity, min_id=last_id, limit=chat_config.max_messages
        ):
            messages.append(msg)

        if messages:
            self._state["last_ids"][str(chat_config.chat_id)] = messages[0].id
            self._save_state()

        return messages

    async def get_for_period(self, chat_config: ChatConfig, period: str) -> list:
        """Получить сообщения за период: '2d', '1w', '12h'"""
        entity = await self._resolve_chat(chat_config)
        offset = self._parse_period(period)

        messages = []
        async for msg in self.client.iter_messages(
            entity, offset_date=datetime.now() - offset,
            limit=chat_config.max_messages
        ):
            messages.append(msg)
        return messages

    async def collect_all_unread(self) -> dict:
        """Собрать непрочитанные из всех чатов"""
        result = {}
        for chat in self.config.chats:
            msgs = await self.get_unread(chat)
            if msgs:
                result[chat.display_name] = (chat, msgs)
        return result

    async def _resolve_chat(self, chat_config):
        if chat_config.chat_id:
            return chat_config.chat_id
        return await self.client.get_entity(chat_config.identifier)

    def _parse_period(self, period: str) -> timedelta:
        num = int(period[:-1])
        unit = period[-1]
        if unit == 'h': return timedelta(hours=num)
        if unit == 'd': return timedelta(days=num)
        if unit == 'w': return timedelta(weeks=num)
        return timedelta(days=1)
```

### 3. assistant/summarizer.py (~120 строк)

```python
"""Генерация summary через GPT-4o"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from openai import OpenAI
from config import config as app_config

@dataclass
class ChatSummary:
    chat_name: str
    priority: str
    summary: str
    actions: list[str]
    message_count: int

@dataclass
class FullSummary:
    chats: list[ChatSummary]
    aggregate: str
    generated_at: datetime

class Summarizer:
    def __init__(self, assistant_config):
        self.config = assistant_config
        self._client = None

    def _get_client(self) -> OpenAI:
        if not self._client:
            self._client = OpenAI(
                api_key=app_config.get("openai_api_key"),
                timeout=120.0
            )
        return self._client

    async def summarize_chat(self, chat_config, messages) -> ChatSummary:
        """Summary одного чата"""
        if not messages:
            return ChatSummary(chat_config.display_name, chat_config.priority,
                             "Нет новых сообщений", [], 0)

        messages_text = self._format_messages(messages)
        prompt = self._build_prompt(chat_config, messages_text)

        response = await asyncio.to_thread(self._call_gpt, prompt)
        actions = self._extract_actions(response)

        return ChatSummary(
            chat_name=chat_config.display_name,
            priority=chat_config.priority,
            summary=response,
            actions=actions,
            message_count=len(messages)
        )

    async def generate_full(self, messages_by_chat: dict) -> FullSummary:
        """Полный summary всех чатов"""
        summaries = []
        for name, (chat_config, msgs) in messages_by_chat.items():
            s = await self.summarize_chat(chat_config, msgs)
            summaries.append(s)

        aggregate = self._build_aggregate(summaries)
        return FullSummary(summaries, aggregate, datetime.now())

    def _build_prompt(self, chat_config, messages_text: str) -> str:
        return f"""Summarize these Telegram messages in Russian.

Chat: {chat_config.display_name}
Context: {chat_config.context}
User goals: {', '.join(self.config.user.goals)}
Keywords to highlight: {', '.join(chat_config.keywords)}

Messages:
{messages_text}

Provide:
1. Brief summary (2-3 sentences)
2. Action items if any (mark urgency)
3. Messages needing response

Be concise. Output in Russian."""

    def _call_gpt(self, prompt: str) -> str:
        resp = self._get_client().chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )
        return resp.choices[0].message.content

    def _format_messages(self, messages) -> str:
        lines = []
        for m in reversed(messages):  # chronological
            sender = getattr(m.sender, 'first_name', 'Unknown') if m.sender else 'Unknown'
            lines.append(f"[{sender}]: {m.text or '[media]'}")
        return "\n".join(lines[-50:])  # last 50

    def _extract_actions(self, text: str) -> list:
        # Simple extraction - lines starting with - or •
        return [l.strip("- •") for l in text.split("\n")
                if l.strip().startswith(("-", "•"))]

    def _build_aggregate(self, summaries: list) -> str:
        # Group by priority
        by_priority = {"high": [], "medium": [], "low": []}
        for s in summaries:
            by_priority.get(s.priority, by_priority["medium"]).append(s)

        lines = [f"📊 <b>Сводка за {datetime.now().strftime('%d.%m.%Y %H:%M')}</b>\n"]

        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        names = {"high": "Высокий приоритет", "medium": "Средний", "low": "Низкий"}

        for p in ["high", "medium", "low"]:
            if by_priority[p]:
                lines.append(f"\n<b>{icons[p]} {names[p]}</b>")
                for s in by_priority[p]:
                    lines.append(f"\n<b>{s.chat_name}</b> ({s.message_count} сообщ.)")
                    lines.append(s.summary)
                    if s.actions:
                        lines.append("<i>Действия:</i>")
                        for a in s.actions[:3]:
                            lines.append(f"  • {a}")

        return "\n".join(lines)
```

### 4. assistant/bot.py (~100 строк)

```python
"""Telegram Bot команды для ассистента"""
import asyncio
import aiohttp
import logging

logger = logging.getLogger(__name__)

class AssistantBot:
    def __init__(self, bot_token: str, chat_id: str, collector, summarizer, storage):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.collector = collector
        self.summarizer = summarizer
        self.storage = storage
        self._last_update_id = 0
        self._running = False

    async def start(self):
        """Запустить polling команд"""
        self._running = True
        logger.info("Assistant bot started, waiting for commands...")

        while self._running:
            try:
                await self._poll_updates()
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)

    async def stop(self):
        self._running = False

    async def _poll_updates(self):
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 30}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=35) as resp:
                data = await resp.json()

        for update in data.get("result", []):
            self._last_update_id = update["update_id"]
            await self._handle(update)

    async def _handle(self, update: dict):
        msg = update.get("message", {})
        text = msg.get("text", "")
        from_id = str(msg.get("chat", {}).get("id"))

        # Only respond to configured user
        if from_id != self.chat_id:
            return

        if text.startswith("/summary"):
            await self._cmd_summary()
        elif text.startswith("/chat "):
            await self._cmd_chat(text)
        elif text == "/help":
            await self._cmd_help()

    async def _cmd_summary(self):
        """Обработка /summary"""
        await self._send("⏳ Собираю сообщения...")

        messages = await self.collector.collect_all_unread()
        if not messages:
            await self._send("✅ Нет новых сообщений")
            return

        await self._send("🤖 Генерирую summary...")
        summary = await self.summarizer.generate_full(messages)

        await self._send(summary.aggregate, parse_mode="HTML")
        await self.storage.save(summary)

    async def _cmd_chat(self, text: str):
        """/chat [name] [period] - например /chat Работа 2d"""
        parts = text.split()
        if len(parts) < 2:
            await self._send("Использование: /chat [название] [период]\nПример: /chat Работа 2d")
            return

        name = parts[1]
        period = parts[2] if len(parts) > 2 else "1d"

        chat_config = self.collector.config.get_chat(name)
        if not chat_config:
            names = [c.display_name for c in self.collector.config.chats]
            await self._send(f"Чат '{name}' не найден.\nДоступные: {', '.join(names)}")
            return

        await self._send(f"⏳ Собираю сообщения из {name} за {period}...")
        messages = await self.collector.get_for_period(chat_config, period)

        summary = await self.summarizer.summarize_chat(chat_config, messages)
        await self._send(f"<b>{summary.chat_name}</b>\n\n{summary.summary}", parse_mode="HTML")

    async def _cmd_help(self):
        await self._send(
            "<b>Команды:</b>\n"
            "/summary - сводка непрочитанных\n"
            "/chat [имя] [период] - сводка чата\n"
            "  Примеры периодов: 12h, 2d, 1w",
            parse_mode="HTML"
        )

    async def _send(self, text: str, parse_mode: str = None):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to send: {await resp.text()}")
```

### 5. assistant/storage.py (~60 строк)

```python
"""Сохранение истории summary"""
from pathlib import Path
from datetime import datetime

class SummaryStorage:
    def __init__(self, data_dir: str = "./data"):
        self.dir = Path(data_dir) / "summaries"
        self.dir.mkdir(parents=True, exist_ok=True)

    async def save(self, summary) -> Path:
        """Сохранить summary в markdown файл"""
        date_str = summary.generated_at.strftime("%Y-%m-%d")
        time_str = summary.generated_at.strftime("%H-%M")

        filename = f"{date_str}_{time_str}.md"
        filepath = self.dir / filename

        content = self._to_markdown(summary)
        filepath.write_text(content, encoding="utf-8")

        return filepath

    def _to_markdown(self, summary) -> str:
        lines = [
            f"# Summary {summary.generated_at.strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Aggregate",
            summary.aggregate.replace("<b>", "**").replace("</b>", "**")
                           .replace("<i>", "_").replace("</i>", "_"),
            "",
            "---",
            "",
            "## По чатам",
        ]

        for s in summary.chats:
            lines.extend([
                f"### {s.chat_name} ({s.priority})",
                f"Сообщений: {s.message_count}",
                "",
                s.summary,
                ""
            ])
            if s.actions:
                lines.append("**Действия:**")
                for a in s.actions:
                    lines.append(f"- {a}")
                lines.append("")

        return "\n".join(lines)

    def cleanup(self, keep_days: int = 30):
        """Удалить старые файлы"""
        cutoff = datetime.now().timestamp() - (keep_days * 86400)
        for f in self.dir.glob("*.md"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
```

### 6. assistant/__init__.py (~30 строк)

```python
"""Personal Assistant module"""
import asyncio
import logging
from .config import AssistantConfig
from .collector import MessageCollector
from .summarizer import Summarizer
from .bot import AssistantBot
from .storage import SummaryStorage

logger = logging.getLogger(__name__)

async def start_assistant(client, bot_token: str, chat_id: str, config_path: str = "assistant_config.yaml"):
    """Запустить ассистента - вызывать из main.py"""
    try:
        config = AssistantConfig.load(config_path)
        logger.info(f"Assistant config loaded: {len(config.chats)} chats")
    except FileNotFoundError:
        logger.info("assistant_config.yaml not found, assistant disabled")
        return None
    except Exception as e:
        logger.error(f"Failed to load assistant config: {e}")
        return None

    collector = MessageCollector(client, config)
    summarizer = Summarizer(config)
    storage = SummaryStorage(config.data_dir)

    bot = AssistantBot(bot_token, chat_id, collector, summarizer, storage)

    # Запуск в фоне
    asyncio.create_task(bot.start())
    logger.info("Personal Assistant started")

    return bot
```

---

## Изменения в main.py

После строки 154 (`register_voice_handler(client)`):

```python
from assistant import start_assistant

# Start personal assistant (if configured)
assistant_bot = await start_assistant(
    client,
    bot_token=config.get("health_bot_token"),
    chat_id=config.get("health_alert_chat_id")
)
```

---

## assistant_config.yaml (пример)

```yaml
user:
  name: "Ренат"
  goals:
    - "Фокус на рабочих задачах"
    - "Быстро отвечать семье"
  language: "ru"

chats:
  - identifier: "@my_work_chat"
    display_name: "Работа"
    context: "Рабочий чат команды. Важны задачи и дедлайны."
    priority: high
    keywords:
      - "срочно"
      - "дедлайн"
      - "ревью"
    max_messages: 100

  - chat_id: -1001234567890
    display_name: "Семья"
    context: "Семейный чат"
    priority: high
    max_messages: 50

  - identifier: "@tech_channel"
    display_name: "Tech News"
    context: "Новости индустрии, низкий приоритет"
    priority: low
    max_messages: 30

data_dir: "./data"
```

---

## requirements.txt

Добавить:
```
pyyaml>=6.0
```

---

## Фазы реализации

### Фаза 1: Каркас
- [ ] Создать папку `assistant/`
- [ ] `assistant/config.py` - dataclasses и загрузка YAML
- [ ] `assistant_config.yaml` - пример конфига
- [ ] Добавить pyyaml в requirements

### Фаза 2: Сбор сообщений
- [ ] `assistant/collector.py` - MessageCollector
- [ ] Тест: получить сообщения из чата

### Фаза 3: Summary
- [ ] `assistant/summarizer.py` - Summarizer с GPT-4o
- [ ] Тест: сгенерировать summary

### Фаза 4: Бот и интеграция
- [ ] `assistant/bot.py` - AssistantBot
- [ ] `assistant/__init__.py` - start_assistant()
- [ ] Интеграция в main.py
- [ ] Тест: /summary и /chat команды

### Фаза 5: Хранение
- [ ] `assistant/storage.py` - SummaryStorage
- [ ] Тест: сохранение в файлы

---

## Верификация

1. Создать `assistant_config.yaml` с реальным чатом
2. Запустить `python main.py`
3. Отправить `/help` боту → должен ответить списком команд
4. Отправить `/summary` → сводка непрочитанных
5. Отправить `/chat Работа 2d` → summary за 2 дня
6. Проверить `data/summaries/` → должен быть .md файл
