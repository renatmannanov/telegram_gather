"""
Database layer for fragments collection.
Uses asyncpg with connection pool for async INSERT into ayda_think's PostgreSQL.
"""
import asyncpg
import json
import logging
from datetime import timezone

logger = logging.getLogger(__name__)


class FragmentsDB:
    def __init__(self):
        self.pool = None

    async def connect(self, database_url: str):
        """Create connection pool. Also creates gather_state table if not exists."""
        self.pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=3
        )
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS gather_state (
                    source VARCHAR(100) PRIMARY KEY,
                    last_msg_id BIGINT,
                    last_collected_at TIMESTAMP DEFAULT NOW()
                )
            """)
        logger.info("FragmentsDB connected, gather_state ready")

    async def insert_fragment(self, external_id, source, text_content,
                              created_at, tags, content_type, metadata,
                              sender_id=None, channel_id=None,
                              message_thread_id=None) -> bool:
        """INSERT a fragment. Returns True if inserted, False if duplicate.

        tags: list[str] -> PostgreSQL TEXT[]
        metadata: dict -> PostgreSQL JSONB (json.dumps applied here)
        """
        # Ensure created_at is timezone-naive UTC for PostgreSQL TIMESTAMP column
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                INSERT INTO fragments (external_id, source, text, created_at,
                                       tags, content_type, metadata,
                                       sender_id, channel_id, message_thread_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
                ON CONFLICT (external_id) DO NOTHING
            """, external_id, source, text_content, created_at,
                tags, content_type, json.dumps(metadata),
                sender_id, channel_id, message_thread_id)
            return result == 'INSERT 0 1'

    async def get_last_id(self, source: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_msg_id FROM gather_state WHERE source = $1",
                source
            )
            return row['last_msg_id'] if row else 0

    async def save_last_id(self, source: str, msg_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO gather_state (source, last_msg_id, last_collected_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (source) DO UPDATE SET
                    last_msg_id = $2,
                    last_collected_at = NOW()
            """, source, msg_id)

    async def get_all_status(self) -> list:
        """Get collection status for all sources."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source, last_msg_id, last_collected_at FROM gather_state ORDER BY source"
            )
            return [dict(r) for r in rows]

    async def close(self):
        if self.pool:
            await self.pool.close()
