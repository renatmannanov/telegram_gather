"""
fetch_contacts.py - Export Telegram group members with bios.
Uses existing Telethon session via config.py.

Usage:
    python fetch_contacts.py "WNDR chat" --output data/exports/wndr
"""
import argparse
import asyncio
import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError, FloodWaitError
from telethon.tl.functions.users import GetFullUserRequest

from config import config

logger = logging.getLogger(__name__)


async def resolve_chat(client: TelegramClient, name: str):
    """Resolve chat name to entity by searching dialogs."""
    name_stripped = name.strip()
    if name_stripped.startswith(("@", "https://", "http://", "t.me/")):
        return await client.get_entity(name_stripped)
    async for dialog in client.iter_dialogs():
        if dialog.title and dialog.title.lower() == name_stripped.lower():
            return dialog.entity
    return await client.get_entity(name_stripped)


async def get_participants_direct(client, entity):
    """Try to get participants via get_participants (needs admin in supergroups)."""
    participants = []
    async for user in client.iter_participants(entity):
        participants.append({
            "user_id": user.id,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username,
        })
    return participants


async def get_participants_from_messages(client, entity, limit=5000):
    """Fallback: collect unique senders from messages."""
    seen = {}
    count = 0
    print(f"  Collecting senders from messages (limit={limit})...")
    async for msg in client.iter_messages(entity, limit=limit):
        if msg.sender_id and msg.sender_id not in seen:
            sender = msg.sender
            if sender and hasattr(sender, 'first_name'):
                seen[msg.sender_id] = {
                    "user_id": msg.sender_id,
                    "first_name": getattr(sender, 'first_name', '') or "",
                    "last_name": getattr(sender, 'last_name', '') or "",
                    "username": getattr(sender, 'username', None),
                }
        count += 1
        if count % 1000 == 0:
            print(f"    ...scanned {count} messages, found {len(seen)} unique senders")
            await asyncio.sleep(0.3)
    print(f"  Scanned {count} messages, found {len(seen)} unique senders")
    return list(seen.values())


async def enrich_with_bios(client, participants):
    """Add bio to each participant via GetFullUserRequest."""
    total = len(participants)
    print(f"  Fetching bios for {total} participants...")
    for i, p in enumerate(participants):
        try:
            full = await client(GetFullUserRequest(p["user_id"]))
            p["bio"] = full.full_user.about or ""
        except FloodWaitError as e:
            print(f"  FloodWait: sleeping {e.seconds}s...")
            await asyncio.sleep(e.seconds + 1)
            try:
                full = await client(GetFullUserRequest(p["user_id"]))
                p["bio"] = full.full_user.about or ""
            except Exception:
                p["bio"] = ""
        except Exception as e:
            logger.warning(f"Failed to get bio for {p['user_id']}: {e}")
            p["bio"] = ""

        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"    ...{i + 1}/{total}")
        await asyncio.sleep(1)  # conservative rate limit

    return participants


def parse_args():
    parser = argparse.ArgumentParser(description="Export Telegram group members with bios")
    parser.add_argument("chat", help="Chat name or identifier")
    parser.add_argument("-o", "--output", default="data/exports/wndr", help="Output directory")
    parser.add_argument("--skip-bios", action="store_true", help="Skip fetching bios (faster)")
    return parser.parse_args()


async def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = TelegramClient(config["session_name"], config["api_id"], config["api_hash"])
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: Session not authorized.", file=sys.stderr)
        await client.disconnect()
        sys.exit(1)

    try:
        print(f"Resolving chat: {args.chat}")
        entity = await resolve_chat(client, args.chat)
        print(f"  Found: {getattr(entity, 'title', entity)}")

        # Try direct participant list first
        participants = []
        try:
            print("  Trying get_participants...")
            participants = await get_participants_direct(client, entity)
            print(f"  Got {len(participants)} participants via get_participants")
        except ChatAdminRequiredError:
            print("  No admin rights — falling back to message senders")
            participants = await get_participants_from_messages(client, entity)
        except Exception as e:
            print(f"  get_participants failed ({e}) — falling back to message senders")
            participants = await get_participants_from_messages(client, entity)

        # Enrich with bios
        if not args.skip_bios:
            participants = await enrich_with_bios(client, participants)

        # Save
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / "wndr_participants.json"

        data = {
            "chat_name": args.chat,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "total_members": len(participants),
            "participants": participants,
        }
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved {len(participants)} participants to {filepath}")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
