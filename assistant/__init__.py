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
    config_path: str = "assistant_config.yaml",
    fragment_collector=None
) -> Optional[AssistantBot]:
    """
    Start the Personal Assistant.

    Args:
        client: Telethon client for reading messages
        bot_token: Telegram Bot API token (same as health_monitor)
        chat_id: Chat ID to send summaries to (same as health_monitor)
        config_path: Path to assistant_config.yaml
        fragment_collector: FragmentCollector instance for /collect commands

    Returns:
        AssistantBot instance if started successfully, None otherwise
    """
    # Check prerequisites
    if not bot_token or not chat_id:
        logger.info("Assistant disabled: HEALTH_BOT_TOKEN or HEALTH_ALERT_CHAT_ID not set")
        return None

    # Load assistant config (optional — bot works without it for /collect commands)
    config = None
    msg_collector = None
    summarizer = None
    storage = None

    if os.path.exists(config_path):
        try:
            config = AssistantConfig.load(config_path)
            logger.info(f"Assistant config loaded: {len(config.chats)} chats configured")
            msg_collector = MessageCollector(client, config)
            summarizer = Summarizer(config)
            storage = SummaryStorage(config.data_dir)
        except Exception as e:
            logger.error(f"Failed to load assistant config: {e}")
    else:
        logger.info(f"Assistant config not found ({config_path}), summary commands disabled")

    # Need at least one feature to start the bot
    if not msg_collector and not fragment_collector:
        logger.info("Assistant disabled: no config and no fragment collector")
        return None

    # Create and start bot
    bot = AssistantBot(
        bot_token=bot_token,
        chat_id=chat_id,
        collector=msg_collector,
        summarizer=summarizer,
        storage=storage,
        fragment_collector=fragment_collector
    )

    # Start polling in background
    asyncio.create_task(bot.start())
    logger.info("Assistant bot started - send /help for commands")

    return bot
