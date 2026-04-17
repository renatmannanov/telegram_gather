"""
Fragment collector: reads messages from Telegram sources and writes to PostgreSQL.
"""
import logging
import re

from telethon.tl.types import MessageReplyHeader

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://\S+')


def get_topic_id(message, chat=None):
    """Return topic ID for a message in a forum group.

    - Named topic: service message ID (e.g. 3, 15)
    - General topic: 1
    - Regular group / not a forum: None

    chat — chat entity (needed to detect General topic).
    """
    reply = message.reply_to

    if isinstance(reply, MessageReplyHeader) and reply.forum_topic:
        if reply.reply_to_top_id is not None:
            return reply.reply_to_top_id
        else:
            return reply.reply_to_msg_id

    if chat is not None and getattr(chat, 'forum', False):
        return 1  # General topic

    return None


class FragmentCollector:
    """Collects messages from Telegram and inserts into PostgreSQL."""

    def __init__(self, client, db):
        self.client = client  # TelegramClient
        self.db = db          # FragmentsDB
        self._bulk_stop = False

    async def collect_new(self, sources: list) -> dict:
        """Collect new messages from given sources. Returns stats."""
        stats = {'inserted': 0, 'skipped': 0}

        for source in sources:
            source_key = str(source)
            last_id = await self.db.get_last_id(source_key)
            max_id = last_id

            # Resolve chat entity once per source (needed for forum detection)
            chat_entity = await self.client.get_entity(source) if source != 'me' else None
            is_forum = getattr(chat_entity, 'forum', False) if chat_entity else False

            async for msg in self.client.iter_messages(
                source, min_id=last_id, reverse=True
            ):
                if not msg.text:
                    continue
                if len(msg.text.strip()) < 10 and not URL_PATTERN.search(msg.text):
                    continue

                thread_id = get_topic_id(msg, chat=chat_entity) if is_forum else None

                inserted = await self.db.insert_fragment(
                    external_id=f"telegram_{source_key}_{msg.id}",
                    source='telegram',
                    text_content=msg.text,
                    created_at=msg.date,
                    tags=self._extract_tags(msg.text),
                    content_type=self._detect_type(msg),
                    metadata={
                        'telegram_msg_id': msg.id,
                        'chat': source_key,
                        'is_forward': msg.forward is not None
                    },
                    sender_id=msg.sender_id,
                    channel_id=int(source_key) if source_key != 'me' else None,
                    message_thread_id=thread_id,
                )
                if inserted:
                    stats['inserted'] += 1
                else:
                    stats['skipped'] += 1

                max_id = max(max_id, msg.id)

            if max_id > last_id:
                await self.db.save_last_id(source_key, max_id)

        return stats

    async def resolve_source(self, name: str):
        """Resolve source by name or ID. Returns (entity, source_key)."""
        name = name.strip()
        # Numeric ID
        if name.lstrip('-').isdigit():
            entity = int(name)
            return entity, str(entity)
        # 'me' shortcut
        if name.lower() == 'me':
            return 'me', 'me'
        # Search dialogs by title (use dialog.id for -100 channel format)
        async for dialog in self.client.iter_dialogs():
            if dialog.title and dialog.title.lower() == name.lower():
                return dialog.entity, str(dialog.id)
        raise ValueError(f"Chat '{name}' not found")

    async def bulk_collect(self, source, source_key=None, progress_callback=None, batch_size=100) -> dict:
        """Collect entire message history from a source. Returns stats."""
        self._bulk_stop = False

        if source_key is None:
            source_key = str(source)

        stats = {'count': 0, 'inserted': 0}
        last_id = await self.db.get_last_id(source_key)

        # Resolve chat entity once (needed for forum detection)
        chat_entity = await self.client.get_entity(source) if source != 'me' else None
        is_forum = getattr(chat_entity, 'forum', False) if chat_entity else False

        logger.info(f"[{source_key}] Bulk collection started (min_id={last_id})")

        async for msg in self.client.iter_messages(source, min_id=last_id, reverse=True):
            if self._bulk_stop:
                logger.info(f"[{source_key}] Bulk collection stopped by user")
                break

            if not msg.text:
                continue
            if len(msg.text.strip()) < 10 and not self._has_url(msg.text):
                continue

            thread_id = get_topic_id(msg, chat=chat_entity) if is_forum else None

            result = await self.db.insert_fragment(
                external_id=f"telegram_{source_key}_{msg.id}",
                source='telegram',
                text_content=msg.text,
                created_at=msg.date,
                tags=self._extract_tags(msg.text),
                content_type=self._detect_type(msg),
                metadata={
                    'telegram_msg_id': msg.id,
                    'chat': source_key,
                    'is_forward': msg.forward is not None
                },
                sender_id=msg.sender_id,
                channel_id=int(source_key) if source_key != 'me' else None,
                message_thread_id=thread_id,
            )
            stats['count'] += 1
            if result:
                stats['inserted'] += 1

            await self.db.save_last_id(source_key, msg.id)

            if stats['count'] % batch_size == 0:
                logger.info(f"  [{source_key}] Processed {stats['count']}, inserted {stats['inserted']}")
                if progress_callback:
                    await progress_callback(stats['count'], stats['inserted'])

        logger.info(f"[{source_key}] Done: {stats['count']} processed, {stats['inserted']} inserted")
        return stats

    def _has_url(self, text: str) -> bool:
        return bool(URL_PATTERN.search(text))

    def _extract_tags(self, text: str) -> list:
        return [w for w in text.split() if w.startswith('#')]

    def _detect_type(self, msg) -> str:
        if msg.forward is not None:
            return 'repost'
        if URL_PATTERN.search(msg.text):
            return 'link'
        return 'note'
