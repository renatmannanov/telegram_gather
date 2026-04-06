"""
Telegram Gather - Personal Telegram Assistant
Userbot that transcribes voice messages and provides AI-powered chat summaries
"""
import logging
import asyncio
import base64
import zlib
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import config, parse_sources
from handlers import register_voice_handler
from services.health_monitor import HealthMonitor, is_session_error
from assistant import start_assistant
from fragments.db import FragmentsDB
from fragments.collector import FragmentCollector
from telethon import events

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def auth_with_qr(client: TelegramClient):
    """Authenticate using QR code"""
    import qrcode

    qr_login = await client.qr_login()

    print("\n" + "=" * 50)
    print("Scan this QR code with Telegram app:")
    print("Settings -> Devices -> Link Desktop Device")
    print("=" * 50 + "\n")

    # Generate and display QR code in terminal
    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(qr_login.url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

    print("\n" + "=" * 50)

    # Wait for scan
    try:
        await qr_login.wait(timeout=60)
        return True
    except asyncio.TimeoutError:
        print("QR code expired. Please restart and try again.")
        return False
    except SessionPasswordNeededError:
        # 2FA enabled
        password = input("Enter your 2FA password: ")
        await client.sign_in(password=password)
        return True


async def auth_with_code(client: TelegramClient):
    """Authenticate using phone code"""
    await client.send_code_request(config["phone"])

    try:
        code = input("Enter the code you received: ")
        await client.sign_in(config["phone"], code)

    except SessionPasswordNeededError:
        password = input("Enter your 2FA password: ")
        await client.sign_in(password=password)


def restore_session_from_env():
    """Restore session file from base64-encoded (and optionally compressed) environment variable"""
    session_data = os.getenv("TELEGRAM_SESSION_BASE64")
    if session_data:
        session_file = f"{config['session_name']}.session"
        logger.info(f"Session env var found ({len(session_data)} chars), target file: {session_file}")
        if os.path.exists(session_file):
            # Always overwrite — env var is the source of truth in deployed environments
            logger.info(f"Session file exists, overwriting with env var data")
        if True:
            logger.info("Restoring session from environment variable...")
            try:
                decoded = base64.b64decode(session_data)
                # Try to decompress (if compressed with zlib)
                try:
                    decoded = zlib.decompress(decoded)
                    logger.info("Session was compressed, decompressed successfully")
                except zlib.error:
                    # Not compressed, use as-is
                    pass
                with open(session_file, "wb") as f:
                    f.write(decoded)
                logger.info("Session restored successfully")
            except Exception as e:
                logger.error(f"Failed to restore session: {e}")
    else:
        logger.info("TELEGRAM_SESSION_BASE64 not set, using local session file")


async def main():
    """Main entry point"""
    logger.info("Starting Telegram Gather...")

    fragments_db = None
    api_runner = None

    # Try to restore session from environment (for Railway/Docker deployment)
    restore_session_from_env()

    # Initialize health monitor
    health_monitor = HealthMonitor(
        bot_token=config.get("health_bot_token"),
        alert_chat_id=config.get("health_alert_chat_id")
    )

    if health_monitor.is_configured:
        logger.info("Health monitoring enabled")
    else:
        logger.info("Health monitoring disabled (HEALTH_BOT_TOKEN or HEALTH_ALERT_CHAT_ID not set)")

    # Create Telethon client
    client = TelegramClient(
        config["session_name"],
        config["api_id"],
        config["api_hash"]
    )

    try:
        # Connect and authenticate
        await client.connect()

        if not await client.is_user_authorized():
            logger.info("Authorization required...")

            # Check if we're in non-interactive mode (e.g., Railway)
            if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("NON_INTERACTIVE"):
                error_msg = "Session expired and running in non-interactive mode. Please re-authorize locally."
                logger.error(error_msg)
                await health_monitor.on_session_error(Exception(error_msg))
                return

            # Ask user for auth method
            print("\nChoose authentication method:")
            print("1. QR code (recommended)")
            print("2. Phone code")
            choice = input("Enter 1 or 2: ").strip()

            if choice == "2":
                await auth_with_code(client)
            else:
                success = await auth_with_qr(client)
                if not success:
                    return

        # Get current user info
        me = await client.get_me()
        logger.info(f"Logged in as: {me.first_name} (@{me.username})")

        # Send startup notification
        await health_monitor.on_startup(me.username or me.first_name)

        # Register handlers
        register_voice_handler(client)

        # Start fragment collection (if DATABASE_URL configured)
        fragment_collector = None
        if config.get("database_url"):
            try:
                fragments_db = FragmentsDB()
                await fragments_db.connect(config["database_url"])
                fragment_collector = FragmentCollector(client, fragments_db)

                # Realtime: event handler for all GATHER_SOURCES
                my_id = me.id
                all_sources = parse_sources(config["gather_sources_raw"])

                # Build chats list for event filter
                event_chats = []
                for s in all_sources:
                    if s == 'me':
                        event_chats.append('me')
                    else:
                        event_chats.append(int(s) if str(s).lstrip('-').isdigit() else s)

                @client.on(events.NewMessage(chats=event_chats))
                async def on_new_fragment(event):
                    msg = event.message
                    if not msg.text:
                        return
                    if len(msg.text.strip()) < 10 and not fragment_collector._has_url(msg.text):
                        return

                    # Determine source key
                    chat_id = event.chat_id
                    if chat_id == my_id:
                        source_key = 'me'
                    else:
                        source_key = str(chat_id)

                    result = await fragment_collector.db.insert_fragment(
                        external_id=f"telegram_{source_key}_{msg.id}",
                        source='telegram',
                        text_content=msg.text,
                        created_at=msg.date,
                        tags=fragment_collector._extract_tags(msg.text),
                        content_type=fragment_collector._detect_type(msg),
                        metadata={
                            'telegram_msg_id': msg.id,
                            'chat': source_key,
                            'is_forward': msg.forward is not None
                        }
                    )
                    if result:
                        await fragment_collector.db.save_last_id(source_key, msg.id)
                        logger.info(f"Fragment saved (realtime): {source_key}_{msg.id}")

                logger.info(f"Fragment collection enabled (realtime for {len(event_chats)} source(s))")
            except Exception as e:
                logger.error(f"Failed to start fragment collection: {e}")
        else:
            logger.info("Fragment collection disabled (DATABASE_URL not set)")

        # Start personal assistant bot (with fragment collector if available)
        assistant_bot = await start_assistant(
            client,
            bot_token=config.get("health_bot_token"),
            chat_id=config.get("health_alert_chat_id"),
            fragment_collector=fragment_collector
        )

        # Start HTTP API (if TG_GATHER_API_KEY is set)
        from api import start_api
        api_runner = await start_api(client, port=int(os.getenv("PORT", "8080")))

        logger.info("Telegram Gather is running. Press Ctrl+C to stop.")

        # Run until disconnected
        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"Error: {e}")

        # Check if it's a session-related error
        if is_session_error(e):
            await health_monitor.on_session_error(e)
        else:
            # Generic error, still notify
            await health_monitor.on_session_error(e)

        raise

    finally:
        # Cleanup HTTP API
        if api_runner:
            await api_runner.cleanup()

        # Cleanup fragment DB pool
        if fragments_db:
            await fragments_db.close()

        # Send shutdown notification
        await health_monitor.on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
