"""
fetch_topic.py - Export messages from a forum topic, grouped by threads.
Uses existing Telethon session via config.py.

Usage:
    python fetch_topic.py "WNDR chat" --topic-id 5593 --output data/exports/wndr --name intro
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


def extract_sender(msg):
    """Extract sender info from message."""
    sender = msg.sender
    if not sender:
        return {"user_id": msg.sender_id, "name": "Unknown", "username": None}
    first = getattr(sender, "first_name", "") or ""
    last = getattr(sender, "last_name", "") or ""
    name = f"{first} {last}".strip() or "Unknown"
    return {
        "user_id": msg.sender_id,
        "name": name,
        "username": getattr(sender, "username", None),
    }


async def fetch_topic_messages(client, entity, topic_id, limit=0):
    """Fetch all messages from a forum topic, return as flat list."""
    messages = []
    count = 0
    async for msg in client.iter_messages(entity, reply_to=topic_id, limit=limit or None):
        if not (msg.text or msg.message):
            count += 1
            continue
        sender = extract_sender(msg)
        messages.append({
            "id": msg.id,
            "date": msg.date.strftime("%Y-%m-%dT%H:%M:%S") if msg.date else None,
            "user_id": sender["user_id"],
            "sender_name": sender["name"],
            "username": sender["username"],
            "text": msg.text or msg.message or "",
            "reply_to_msg_id": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        })
        count += 1
        if count % 200 == 0:
            print(f"    ...fetched {count} messages")
            await asyncio.sleep(0.3)

    messages.reverse()  # chronological order (oldest first)
    return messages


def group_into_threads(messages):
    """Group messages into threads: root message + replies."""
    by_id = {m["id"]: m for m in messages}
    threads = {}  # root_id -> {"root": msg, "replies": []}
    orphan_replies = []

    for msg in messages:
        reply_to = msg.get("reply_to_msg_id")
        if reply_to is None:
            # This is a root message (direct reply to topic)
            threads[msg["id"]] = {"root": msg, "replies": []}
        else:
            # Find the root of the thread
            root_id = reply_to
            # Walk up to find the actual root
            visited = set()
            while root_id in by_id and by_id[root_id].get("reply_to_msg_id") and root_id not in visited:
                visited.add(root_id)
                parent = by_id[root_id].get("reply_to_msg_id")
                if parent and parent in by_id:
                    root_id = parent
                else:
                    break

            if root_id in threads:
                threads[root_id]["replies"].append(msg)
            elif root_id in by_id:
                # Root exists but wasn't categorized yet
                threads[root_id] = {"root": by_id[root_id], "replies": [msg]}
            else:
                orphan_replies.append(msg)

    result = list(threads.values())
    if orphan_replies:
        result.append({"root": None, "replies": orphan_replies})
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Export messages from a forum topic")
    parser.add_argument("chat", help="Chat name or identifier")
    parser.add_argument("--topic-id", type=int, required=True, help="Forum topic ID")
    parser.add_argument("--name", required=True, help="Topic name for the output file")
    parser.add_argument("-o", "--output", default="data/exports/wndr", help="Output directory")
    parser.add_argument("-l", "--limit", type=int, default=0, help="Max messages (0 = no limit)")
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

        print(f"  Fetching topic {args.topic_id} messages...")
        messages = await fetch_topic_messages(client, entity, args.topic_id, args.limit)
        print(f"  Got {len(messages)} text messages")

        threads = group_into_threads(messages)
        print(f"  Grouped into {len(threads)} threads")

        # Save
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"wndr_topic_{args.name}.json"

        data = {
            "chat_name": args.chat,
            "topic_id": args.topic_id,
            "topic_name": args.name,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "total_messages": len(messages),
            "total_threads": len(threads),
            "threads": threads,
        }
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved to {filepath}")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
