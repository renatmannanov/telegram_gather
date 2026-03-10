"""
Message Collector - fetches messages from Telegram chats via Telethon
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from telethon import TelegramClient
from telethon.tl.types import Message

from .config import AssistantConfig, ChatConfig

logger = logging.getLogger(__name__)


DEFAULT_FETCH_DAYS = 14  # Always limit messages to last N days


class MessageCollector:
    """Collects messages from monitored Telegram chats"""

    def __init__(self, client: TelegramClient, config: AssistantConfig):
        self.client = client
        self.config = config
        self.state_file = Path(config.data_dir) / "assistant_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load last processed message IDs from state file"""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
        return {"last_ids": {}}

    def _save_state(self):
        """Save state to file"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    async def _resolve_chat(self, chat_config: ChatConfig):
        """
        Resolve chat to entity.

        Supported identifier formats:
        - @username (public chats/channels)
        - https://t.me/username
        - https://t.me/+abc123 (private invite links)
        - https://t.me/c/123456789/1 (private channel links)
        - Chat title (searches in your dialogs)
        - Numeric chat_id
        """
        # By explicit chat_id
        if chat_config.chat_id:
            return chat_config.chat_id

        if chat_config.identifier:
            identifier = chat_config.identifier.strip()

            # Direct resolution for usernames and links
            if identifier.startswith(("@", "https://", "http://", "t.me/")):
                return await self.client.get_entity(identifier)

            # Try to find by title in dialogs
            async for dialog in self.client.iter_dialogs():
                if dialog.title and dialog.title.lower() == identifier.lower():
                    logger.info(f"Resolved '{identifier}' to chat_id {dialog.id}")
                    return dialog.entity

            # If not found by title, try as-is (might be username without @)
            return await self.client.get_entity(identifier)

        raise ValueError(f"Chat {chat_config.display_name} has no identifier or chat_id")

    async def get_unread(self, chat_config: ChatConfig) -> List[Message]:
        """
        Get new messages since last check.
        Always limits to last DEFAULT_FETCH_DAYS days to avoid token overflow.
        Uses min_id additionally to skip already processed messages.
        """
        try:
            entity = await self._resolve_chat(chat_config)
        except Exception as e:
            logger.error(f"Failed to resolve chat {chat_config.display_name}: {e}")
            return []

        chat_key = str(chat_config.chat_id or chat_config.identifier)
        last_id = self._state["last_ids"].get(chat_key, 0)

        # Calculate date range: from N days ago to now
        since_date = datetime.now() - timedelta(days=DEFAULT_FETCH_DAYS)

        messages = []
        try:
            # Use reverse=True to go from oldest to newest, starting from since_date
            async for msg in self.client.iter_messages(
                entity,
                offset_date=since_date,
                min_id=last_id,  # Skip already processed
                reverse=True,
                limit=chat_config.max_messages
            ):
                # Debug: log every message we see
                msg_type = "text"
                if msg.voice:
                    msg_type = "voice"
                elif msg.video_note:
                    msg_type = "video_note"
                elif msg.audio:
                    msg_type = "audio"
                elif msg.media:
                    msg_type = f"media:{type(msg.media).__name__}"

                has_content = bool(msg.text or msg.message or msg.voice or msg.video_note or msg.audio)
                logger.info(f"  msg #{msg.id} type={msg_type} has_content={has_content}")

                # Include text messages, voice messages, video notes, and audio files
                if has_content:
                    messages.append(msg)

            logger.info(
                f"Collected {len(messages)} messages from {chat_config.display_name} "
                f"(since {since_date.strftime('%d.%m.%Y')}, min_id={last_id})"
            )

            # Update last processed ID
            if messages:
                newest_id = max(m.id for m in messages)
                self._state["last_ids"][chat_key] = newest_id
                self._save_state()

        except Exception as e:
            logger.error(f"Failed to fetch messages from {chat_config.display_name}: {e}")

        return messages

    async def get_for_period(
        self,
        chat_config: ChatConfig,
        period: str
    ) -> List[Message]:
        """
        Get messages for a specific time period.
        Period format: '12h', '2d', '1w'
        """
        try:
            entity = await self._resolve_chat(chat_config)
        except Exception as e:
            logger.error(f"Failed to resolve chat {chat_config.display_name}: {e}")
            return []

        offset = self._parse_period(period)
        since = datetime.now() - offset

        messages = []
        try:
            async for msg in self.client.iter_messages(
                entity,
                offset_date=since,
                limit=chat_config.max_messages
            ):
                if msg.text or msg.message:
                    messages.append(msg)

            logger.info(
                f"Collected {len(messages)} messages from {chat_config.display_name} "
                f"for period {period}"
            )

        except Exception as e:
            logger.error(f"Failed to fetch messages from {chat_config.display_name}: {e}")

        return messages

    async def collect_all_unread(self) -> Dict[str, Tuple[ChatConfig, List[Message]]]:
        """
        Collect unread messages from all monitored chats.
        Returns dict: {display_name: (chat_config, messages)}
        """
        result = {}

        for chat_config in self.config.chats:
            messages = await self.get_unread(chat_config)
            if messages:
                result[chat_config.display_name] = (chat_config, messages)

        total = sum(len(msgs) for _, msgs in result.values())
        logger.info(f"Collected {total} total messages from {len(result)} chats")

        return result

    def _parse_period(self, period: str) -> timedelta:
        """
        Parse period string to timedelta.
        Examples: '12h' -> 12 hours, '2d' -> 2 days, '1w' -> 1 week
        """
        if not period:
            return timedelta(days=1)

        try:
            num = int(period[:-1])
            unit = period[-1].lower()

            if unit == 'h':
                return timedelta(hours=num)
            elif unit == 'd':
                return timedelta(days=num)
            elif unit == 'w':
                return timedelta(weeks=num)
            else:
                logger.warning(f"Unknown period unit '{unit}', defaulting to days")
                return timedelta(days=num)

        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse period '{period}': {e}, defaulting to 1 day")
            return timedelta(days=1)

    def reset_state(self, chat_name: Optional[str] = None):
        """
        Reset state (for re-processing messages).
        If chat_name provided, reset only that chat.
        """
        if chat_name:
            chat_config = self.config.get_chat(chat_name)
            if chat_config:
                chat_key = str(chat_config.chat_id or chat_config.identifier)
                self._state["last_ids"].pop(chat_key, None)
        else:
            self._state["last_ids"] = {}

        self._save_state()
        logger.info(f"State reset for: {chat_name or 'all chats'}")
