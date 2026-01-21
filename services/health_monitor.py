"""
Health monitoring service for Telegram Gather
Monitors session status and sends alerts via separate Telegram Bot
"""
import logging
import asyncio
import aiohttp
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors userbot health and sends alerts via Telegram Bot API
    Uses a separate bot token (not userbot) to ensure alerts work even when session is dead
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        alert_chat_id: Optional[str] = None,
        check_interval: int = 60
    ):
        self.bot_token = bot_token
        self.alert_chat_id = alert_chat_id
        self.check_interval = check_interval
        self.is_healthy = True
        self.last_check = None
        self.error_count = 0
        self._running = False

    @property
    def is_configured(self) -> bool:
        """Check if monitoring is properly configured"""
        return bool(self.bot_token and self.alert_chat_id)

    async def send_alert(self, message: str) -> bool:
        """Send alert message via Telegram Bot API"""
        if not self.is_configured:
            logger.warning("Health monitor not configured, skipping alert")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.alert_chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info("Alert sent successfully")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to send alert: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            return False

    async def on_session_error(self, error: Exception) -> None:
        """Called when a session-related error occurs"""
        self.is_healthy = False
        self.error_count += 1

        error_name = type(error).__name__
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            "🚨 <b>Telegram Gather - Session Error</b>\n\n"
            f"⏰ Time: {timestamp}\n"
            f"❌ Error: <code>{error_name}</code>\n"
            f"📝 Details: {str(error)[:200]}\n\n"
            "⚠️ <b>Action required:</b>\n"
            "1. Re-authorize locally: <code>python main.py</code>\n"
            "2. Update session on Railway\n"
            "3. Redeploy the service"
        )

        await self.send_alert(message)

    async def on_disconnect(self) -> None:
        """Called when client disconnects unexpectedly"""
        self.is_healthy = False
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            "⚠️ <b>Telegram Gather - Disconnected</b>\n\n"
            f"⏰ Time: {timestamp}\n"
            "📡 Client disconnected from Telegram\n\n"
            "Attempting to reconnect..."
        )

        await self.send_alert(message)

    async def on_startup(self, username: str) -> None:
        """Called when bot successfully starts"""
        self.is_healthy = True
        self.error_count = 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            "✅ <b>Telegram Gather - Started</b>\n\n"
            f"⏰ Time: {timestamp}\n"
            f"👤 Account: @{username}\n"
            "🎤 Voice transcription is active"
        )

        await self.send_alert(message)

    async def on_shutdown(self) -> None:
        """Called when bot is shutting down"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            "🛑 <b>Telegram Gather - Stopped</b>\n\n"
            f"⏰ Time: {timestamp}\n"
            "Service was stopped"
        )

        await self.send_alert(message)

    def get_status(self) -> dict:
        """Get current health status"""
        return {
            "healthy": self.is_healthy,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "error_count": self.error_count,
            "monitoring_enabled": self.is_configured
        }


# Session-related errors that indicate auth problems
SESSION_ERRORS = (
    "AuthKeyUnregisteredError",
    "AuthKeyInvalidError",
    "SessionRevokedError",
    "SessionExpiredError",
    "UserDeactivatedError",
    "UserDeactivatedBanError",
    "AuthKeyDuplicatedError",
)


def is_session_error(error: Exception) -> bool:
    """Check if error is related to session/auth problems"""
    error_name = type(error).__name__
    return error_name in SESSION_ERRORS
