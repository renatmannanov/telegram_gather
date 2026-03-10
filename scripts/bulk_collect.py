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
import os
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telethon import TelegramClient

from config import config, parse_sources
from fragments.db import FragmentsDB
from fragments.collector import FragmentCollector

logger = logging.getLogger(__name__)


async def bulk_collect(client, db, sources, batch_size=100):
    """Collect entire message history from sources."""
    collector = FragmentCollector(client, db)

    for source in sources:
        source_key = str(source)
        count = 0
        inserted = 0

        logger.info(f"[{source_key}] Starting bulk collection...")

        async for msg in client.iter_messages(source, reverse=True):
            if not msg.text:
                continue
            if len(msg.text.strip()) < 10 and not collector._has_url(msg.text):
                continue

            result = await db.insert_fragment(
                external_id=f"telegram_{source_key}_{msg.id}",
                source='telegram',
                text_content=msg.text,
                created_at=msg.date,
                tags=collector._extract_tags(msg.text),
                content_type=collector._detect_type(msg),
                metadata={
                    'telegram_msg_id': msg.id,
                    'chat': source_key,
                    'is_forward': msg.forward is not None
                }
            )
            count += 1
            if result:
                inserted += 1
            if count % batch_size == 0:
                logger.info(f"  [{source_key}] Processed {count} messages, {inserted} inserted...")

            # Update last_id as we go
            await db.save_last_id(source_key, msg.id)

        logger.info(f"[{source_key}] Done: {count} processed, {inserted} inserted")


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

    try:
        await bulk_collect(client, db, sources)
    finally:
        await db.close()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
