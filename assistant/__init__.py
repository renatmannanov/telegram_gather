"""
Personal Assistant module for Telegram Gather

Provides AI-powered message summaries and action recommendations.
"""
import asyncio
import logging
import os
from typing import Optional

from telethon import TelegramClient

from .config import AssistantConfig
from .collector import MessageCollector
from .summarizer import Summarizer
from .bot import AssistantBot
from .storage import SummaryStorage

logger = logging.getLogger(__name__)

# Module exports
__all__ = [
    "start_assistant",
    "AssistantConfig",
    "MessageCollector",
    "Summarizer",
    "AssistantBot",
    "SummaryStorage",
]


async def start_assistant(
    client: TelegramClient,
    bot_token: str,
    chat_id: str,
    config_path: str = "assistant_config.yaml"
) -> Optional[AssistantBot]:
    """
    Start the Personal Assistant.

    Args:
        client: Telethon client for reading messages
        bot_token: Telegram Bot API token (same as health_monitor)
        chat_id: Chat ID to send summaries to (same as health_monitor)
        config_path: Path to assistant_config.yaml

    Returns:
        AssistantBot instance if started successfully, None otherwise
    """
    # Check prerequisites
    if not bot_token or not chat_id:
        logger.info("Assistant disabled: HEALTH_BOT_TOKEN or HEALTH_ALERT_CHAT_ID not set")
        return None

    if not os.path.exists(config_path):
        logger.info(f"Assistant disabled: {config_path} not found")
        return None

    # Load configuration
    try:
        config = AssistantConfig.load(config_path)
        logger.info(f"Assistant config loaded: {len(config.chats)} chats configured")
    except Exception as e:
        logger.error(f"Failed to load assistant config: {e}")
        return None

    if not config.chats:
        logger.warning("Assistant disabled: no chats configured in assistant_config.yaml")
        return None

    # Initialize components
    collector = MessageCollector(client, config)
    summarizer = Summarizer(config)
    storage = SummaryStorage(config.data_dir)

    # Create and start bot
    bot = AssistantBot(
        bot_token=bot_token,
        chat_id=chat_id,
        collector=collector,
        summarizer=summarizer,
        storage=storage
    )

    # Start polling in background
    asyncio.create_task(bot.start())
    logger.info("Personal Assistant started - send /help to the bot for commands")

    return bot
