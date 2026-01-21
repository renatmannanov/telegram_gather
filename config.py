"""
Configuration loader for Telegram Gather
Loads settings from environment variables
"""
import os
from dotenv import load_dotenv

load_dotenv()


def get_required(key: str) -> str:
    """Get required environment variable or raise error"""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def get_optional(key: str, default: str = None) -> str:
    """Get optional environment variable with default"""
    return os.getenv(key, default)


# Configuration dictionary
config = {
    # Telegram API credentials (from https://my.telegram.org)
    "api_id": int(get_required("TELEGRAM_API_ID")),
    "api_hash": get_required("TELEGRAM_API_HASH"),
    "phone": get_required("TELEGRAM_PHONE"),

    # OpenAI
    "openai_api_key": get_optional("OPENAI_API_KEY"),

    # Transcription settings
    "transcription_language": get_optional("TRANSCRIPTION_LANGUAGE", "ru"),
    "improve_transcription": get_optional("IMPROVE_TRANSCRIPTION", "true").lower() == "true",

    # Session name (for Telethon session file)
    "session_name": get_optional("SESSION_NAME", "telegram_gather"),

    # Health monitoring (optional)
    # Create a bot via @BotFather and get token
    # Get your chat_id by messaging @userinfobot
    "health_bot_token": get_optional("HEALTH_BOT_TOKEN"),
    "health_alert_chat_id": get_optional("HEALTH_ALERT_CHAT_ID"),
}


def get(key: str, default=None):
    """Get config value by key"""
    return config.get(key, default)
