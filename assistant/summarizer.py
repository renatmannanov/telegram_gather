"""
Summarizer - generates AI summaries using GPT-4o
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Tuple

from openai import OpenAI
from telethon.tl.types import Message

from config import config as app_config
from .config import AssistantConfig, ChatConfig

logger = logging.getLogger(__name__)


@dataclass
class MediaItem:
    """A voice/video/audio message"""
    emoji: str  # 🎤 / 🔵 / 🎵
    label: str  # "голосовое", "кружочек", "аудио"
    duration: str  # "1:23" or ""
    link: str  # https://t.me/c/...
    sender: str  # "Дмитрий" or ""


@dataclass
class ChatSummary:
    """Summary for a single chat"""
    chat_name: str
    priority: str
    summary: str
    actions: List[str] = field(default_factory=list)
    message_count: int = 0
    media_items: List[MediaItem] = field(default_factory=list)


@dataclass
class FullSummary:
    """Aggregated summary of all chats"""
    chats: List[ChatSummary]
    aggregate: str
    generated_at: datetime


class Summarizer:
    """Generates summaries using GPT-4o"""

    def __init__(self, config: AssistantConfig):
        self.config = config
        self._client = None

    def _get_client(self) -> OpenAI:
        """Lazy initialization of OpenAI client"""
        if not self._client:
            api_key = app_config.get("openai_api_key")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            self._client = OpenAI(api_key=api_key, timeout=120.0)
        return self._client

    async def summarize_chat(
        self,
        chat_config: ChatConfig,
        messages: List[Message]
    ) -> ChatSummary:
        """Generate summary for a single chat"""
        if not messages:
            return ChatSummary(
                chat_name=chat_config.display_name,
                priority=chat_config.priority,
                summary="Нет новых сообщений",
                actions=[],
                message_count=0,
                media_items=[]
            )

        messages_text, oldest_date, newest_date, media_items = self._format_messages(messages)
        prompt = self._build_chat_prompt(chat_config, messages_text, oldest_date, newest_date)

        try:
            response = await asyncio.to_thread(self._call_gpt, prompt)
            actions = self._extract_actions(response)

            return ChatSummary(
                chat_name=chat_config.display_name,
                priority=chat_config.priority,
                summary=response,
                actions=actions,
                message_count=len(messages),
                media_items=media_items
            )

        except Exception as e:
            logger.error(f"Failed to summarize {chat_config.display_name}: {e}")
            return ChatSummary(
                chat_name=chat_config.display_name,
                priority=chat_config.priority,
                summary=f"Ошибка при создании summary: {e}",
                actions=[],
                message_count=len(messages),
                media_items=media_items
            )

    async def generate_full(
        self,
        messages_by_chat: Dict[str, Tuple[ChatConfig, List[Message]]]
    ) -> FullSummary:
        """Generate full summary for all chats"""
        summaries = []

        for name, (chat_config, msgs) in messages_by_chat.items():
            summary = await self.summarize_chat(chat_config, msgs)
            summaries.append(summary)

        aggregate = self._build_aggregate(summaries)

        return FullSummary(
            chats=summaries,
            aggregate=aggregate,
            generated_at=datetime.now()
        )

    def _build_chat_prompt(
        self,
        chat_config: ChatConfig,
        messages_text: str,
        oldest_date: str,
        newest_date: str
    ) -> str:
        """Build prompt for single chat summary"""
        return f"""Чат: {chat_config.display_name}
Цель пользователя: {chat_config.goal}
Период сообщений: {oldest_date} — {newest_date}
Сегодня: {datetime.now().strftime("%d.%m.%Y")}

Сообщения:
{messages_text}

---

Сделай сводку СТРОГО на основе сообщений выше.

ФОРМАТ ВЫВОДА — Telegram HTML:
- Заголовки: <b>Заголовок</b>
- Ссылки: <a href="URL">текст</a>
- НЕ используй Markdown (**, [], #)

<b>Что происходит</b>
Кратко опиши контекст (2-3 предложения). Что важного случилось или планируется.

<b>Что делать</b>
Формат: • Действие → зачем. Срочность
- Если в сообщениях есть ссылки (Zoom, календарь и т.д.) — ОБЯЗАТЕЛЬНО включи их как <a href="URL">текст</a>
- Срочность: 🔴 сегодня / 🟡 2-3 дня / 🟢 неделя+
- Если действий нет — "—"

ВАЖНО:
- ФОКУС на последних 2-3 днях и ближайших дедлайнах
- Старые события (>3 дней назад) упоминай ТОЛЬКО если они влияют на текущие действия
- Сохраняй ВСЕ ссылки из сообщений
- НЕ выдумывай то, чего нет в сообщениях"""

    def _call_gpt(self, prompt: str) -> str:
        """Synchronous GPT call (runs in thread pool)"""
        response = self._get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()

    def _format_messages(self, messages: List[Message]) -> tuple[str, str, str, List[MediaItem]]:
        """
        Format messages for the prompt.
        Returns: (formatted_text, oldest_date, newest_date, media_items)
        """
        lines = []
        dates = []
        media_items = []

        # Reverse to get chronological order (oldest first)
        for msg in reversed(messages):
            sender_name = "Unknown"
            if msg.sender:
                sender_name = getattr(msg.sender, 'first_name', None) or \
                              getattr(msg.sender, 'username', None) or \
                              "Unknown"

            # Handle different message types
            # For media: sender is empty if Unknown
            media_sender = sender_name if sender_name != "Unknown" else ""

            if msg.voice:
                duration = getattr(msg.voice, 'duration', 0) or 0
                mins, secs = divmod(duration, 60)
                link = self._get_message_link(msg)
                dur_str = f"{mins}:{secs:02d}" if duration else ""
                text = f"[🎤 голосовое]"
                media_items.append(MediaItem(
                    emoji="🎤", label="голосовое", duration=dur_str, link=link, sender=media_sender
                ))
            elif msg.video_note:
                duration = getattr(msg.video_note, 'duration', 0) or 0
                mins, secs = divmod(duration, 60)
                link = self._get_message_link(msg)
                dur_str = f"{mins}:{secs:02d}" if duration else ""
                text = f"[🔵 кружочек]"
                media_items.append(MediaItem(
                    emoji="🔵", label="кружочек", duration=dur_str, link=link, sender=media_sender
                ))
            elif msg.audio:
                duration = getattr(msg.audio, 'duration', 0) or 0
                mins, secs = divmod(duration, 60)
                link = self._get_message_link(msg)
                dur_str = f"{mins}:{secs:02d}" if duration else ""
                text = f"[🎵 аудио]"
                media_items.append(MediaItem(
                    emoji="🎵", label="аудио", duration=dur_str, link=link, sender=media_sender
                ))
            else:
                text = msg.text or msg.message or "[media]"
                # Truncate very long messages
                if len(text) > 500:
                    text = text[:500] + "..."

            timestamp = msg.date.strftime("%d.%m %H:%M") if msg.date else ""
            lines.append(f"[{timestamp}] {sender_name}: {text}")
            if msg.date:
                dates.append(msg.date)

        # Limit to last 30 messages to fit in context
        limited_lines = lines[-30:]

        # Get date range
        oldest = min(dates).strftime("%d.%m.%Y") if dates else "?"
        newest = max(dates).strftime("%d.%m.%Y") if dates else "?"

        return "\n".join(limited_lines), oldest, newest, media_items

    def _get_message_link(self, msg: Message) -> str:
        """Generate link to a specific message"""
        chat_id = msg.chat_id
        # For supergroups/channels, convert to public link format
        if chat_id and chat_id < 0:
            # Remove -100 prefix for supergroups
            chat_id_str = str(abs(chat_id))
            if chat_id_str.startswith("100"):
                chat_id_str = chat_id_str[3:]
            return f"https://t.me/c/{chat_id_str}/{msg.id}"
        return f"(сообщение {msg.id})"

    def _extract_actions(self, text: str) -> List[str]:
        """Extract action items from summary text"""
        actions = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith(("-", "•", "*")):
                # Clean up the bullet point
                action = line.lstrip("-•* ").strip()
                if action and len(action) > 3:
                    actions.append(action)
        return actions[:5]  # Limit to 5 actions

    def _build_aggregate(self, summaries: List[ChatSummary]) -> str:
        """Build aggregate summary grouped by priority"""
        # Group by priority
        by_priority = {"high": [], "medium": [], "low": []}
        for s in summaries:
            priority = s.priority if s.priority in by_priority else "medium"
            by_priority[priority].append(s)

        # Build formatted output
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        lines = [f"<b>Сводка за {now}</b>\n"]

        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        names = {"high": "Высокий приоритет", "medium": "Средний приоритет", "low": "Низкий приоритет"}

        has_content = False
        for priority in ["high", "medium", "low"]:
            chats = by_priority[priority]
            if not chats:
                continue

            has_content = True
            lines.append(f"\n{icons[priority]} <b>{names[priority]}</b>")

            for s in chats:
                lines.append(f"\n<b>{s.chat_name}</b> ({s.message_count} сообщ.)")

                # GPT now generates HTML directly, no escaping needed
                lines.append(s.summary)

                # Add media links section if any
                if s.media_items:
                    lines.append("\n<b>🎧 Аудио/видео</b>")
                    for item in s.media_items:
                        dur_part = f" ({item.duration})" if item.duration else ""
                        sender_part = f" — {item.sender}" if item.sender else ""
                        lines.append(f'{item.emoji} <a href="{item.link}">{item.label}</a>{dur_part}{sender_part}')

        if not has_content:
            lines.append("\nНет новых сообщений в отслеживаемых чатах.")

        return "\n".join(lines)
