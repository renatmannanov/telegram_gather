"""
Voice Handler - processes voice messages in Telegram
Downloads, transcribes, and sends reply with transcription
"""
import os
import logging
import tempfile
from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel, ChannelParticipantAdmin, ChannelParticipantCreator

from config import config
from services import transcribe_audio, improve_transcription, is_transcription_available, TranscriptionError

logger = logging.getLogger(__name__)


def has_voice_or_audio(message) -> bool:
    """Check if message contains voice or audio"""
    return message.voice is not None or message.audio is not None


async def is_allowed_chat(client: TelegramClient, message) -> bool:
    """
    Проверяет, разрешён ли чат для транскрипции:
    - Личные чаты (User) — всегда да
    - Группы из whitelist — да
    - Группы где я создатель или админ — да
    - Остальное — нет
    """
    chat = message.chat

    # 1. Личка — всегда ок
    if isinstance(chat, User):
        return True

    chat_id = message.chat_id

    # 2. Проверка whitelist (ID могут быть с минусом или без)
    allowed_ids = config.get("allowed_group_ids", set())
    if chat_id in allowed_ids or abs(chat_id) in allowed_ids:
        return True

    # 3. Для групп и супергрупп проверяем права создателя/админа
    if isinstance(chat, (Chat, Channel)):
        # Быстрая проверка: creator флаг в chat
        if getattr(chat, 'creator', False):
            return True

        # Детальная проверка через API
        try:
            me = await client.get_me()
            if isinstance(chat, Channel):
                # Супергруппы и каналы
                participant = await client.get_participant(chat, me)
                if isinstance(participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                    return True
        except Exception as e:
            logger.debug(f"Could not check admin rights for {chat_id}: {e}")

    return False


async def download_voice_file(client: TelegramClient, message) -> str:
    """
    Download voice/audio file to temp location

    Args:
        client: Telethon client
        message: Message with voice/audio

    Returns:
        Path to downloaded temp file
    """
    if message.voice:
        suffix = ".ogg"
        media = message.voice
    elif message.audio:
        mime = message.audio.mime_type or ""
        if "mp3" in mime:
            suffix = ".mp3"
        elif "wav" in mime:
            suffix = ".wav"
        elif "m4a" in mime or "mp4" in mime:
            suffix = ".m4a"
        else:
            suffix = ".ogg"
        media = message.audio
    else:
        raise ValueError("Message has no voice or audio")

    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    temp_file.close()

    # Download
    logger.info(f"Downloading voice to {temp_path}")
    await client.download_media(message, temp_path)

    return temp_path


async def process_voice_message(
    client: TelegramClient,
    message,
    improve: bool = True
) -> dict:
    """
    Full voice processing pipeline:
    1. Download audio file
    2. Transcribe with Whisper
    3. Optionally improve with GPT

    Args:
        client: Telethon client
        message: Message with voice/audio
        improve: Whether to improve transcription with GPT

    Returns:
        dict with 'content' (transcribed text) and 'duration' (if available)
    """
    temp_path = None
    try:
        # Download
        temp_path = await download_voice_file(client, message)

        # Get duration (safely)
        duration = None
        if message.voice and hasattr(message.voice, 'duration'):
            duration = message.voice.duration
        elif message.audio and hasattr(message.audio, 'duration'):
            duration = message.audio.duration

        # Transcribe
        text = await transcribe_audio(temp_path)

        # Improve if requested
        if improve and config.get("improve_transcription", True):
            text = await improve_transcription(text)

        return {
            "content": text,
            "duration": duration,
        }

    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")


def register_voice_handler(client: TelegramClient):
    """
    Register voice message handler on Telethon client

    Handles:
    - Incoming voice messages (from others)
    - Outgoing voice messages (your own)
    - Only in private chats (for now)
    """

    @client.on(events.NewMessage(func=lambda e: has_voice_or_audio(e.message)))
    async def voice_handler(event):
        """Handle new voice/audio messages"""
        message = event.message

        # Check if chat is allowed (private, whitelist, or admin/creator)
        if not await is_allowed_chat(client, message):
            logger.debug(f"Skipping voice in non-allowed chat: {message.chat_id}")
            return

        # Check if transcription is available
        if not is_transcription_available():
            logger.warning("Transcription not available - OPENAI_API_KEY not set")
            return

        status_msg = None
        try:
            logger.info(f"Processing voice message {message.id} in chat {message.chat_id}")

            # Send status message immediately (with quote to show original voice)
            status_msg = await message.reply("🎤 Транскрибирую...", quote=True)

            # Process voice
            result = await process_voice_message(client, message, improve=True)
            transcription = result["content"]

            if not transcription:
                logger.warning("Empty transcription result")
                await status_msg.edit("⚠️ Не удалось распознать речь")
                return

            # Check if it's my own message or from someone else
            me = await client.get_me()
            is_outgoing = message.out or (message.sender_id == me.id)

            if is_outgoing:
                # My message - just show transcription
                formatted = f"📄 {transcription}"
            else:
                # Someone else's message - show "сообщение от Name"
                sender = await message.get_sender()
                sender_name = sender.first_name or sender.username or "собеседника"
                formatted = f"📄 Сообщение от {sender_name}:\n{transcription}"

            # Update status message with transcription
            await status_msg.edit(formatted)

            logger.info(f"Transcription sent for message {message.id}")

        except TranscriptionError as e:
            logger.error(f"Transcription failed: {e}")
            if status_msg:
                await status_msg.edit(f"⚠️ {str(e)}")
            else:
                await message.reply(f"⚠️ {str(e)}")

        except Exception as e:
            logger.error(f"Error processing voice message: {e}", exc_info=True)
            if status_msg:
                await status_msg.edit("⚠️ Ошибка при обработке")

    logger.info("Voice handler registered")
