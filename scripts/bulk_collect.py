"""
One-time bulk collection of all message history from Telegram sources.
Separate from main.py — run manually, not on every startup.

Usage:
    python -m scripts.bulk_collect
    python -m scripts.bulk_collect --sources me -1001234567890
"""
import argparse
import asyncio
import io
import logging
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telethon import TelegramClient

from config import config, parse_sources
from fragments.db import FragmentsDB
from fragments.collector import FragmentCollector

logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Bulk collect Telegram message history")
    parser.add_argument(
        "--sources", nargs="*",
        help="Sources to collect from (default: from GATHER_SOURCES env)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    database_url = config.get("database_url")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    if args.sources:
        sources = parse_sources(",".join(args.sources))
    else:
        sources = parse_sources(config.get("gather_sources_raw", ""))

    if not sources:
        logger.error("No sources specified. Use --sources or set GATHER_SOURCES env")
        sys.exit(1)

    logger.info(f"Sources: {sources}")

    client = TelegramClient(config["session_name"], config["api_id"], config["api_hash"])
    await client.connect()

    if not await client.is_user_authorized():
        logger.error("Session not authorized. Run main.py first.")
        await client.disconnect()
        sys.exit(1)

    db = FragmentsDB()
    await db.connect(database_url)
    collector = FragmentCollector(client, db)

    try:
        for source in sources:
            source_key = str(source)
            stats = await collector.bulk_collect(source, source_key=source_key)
            logger.info(f"[{source_key}] Final: {stats}")
    finally:
        await db.close()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
