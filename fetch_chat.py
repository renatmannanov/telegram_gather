"""
fetch_chat.py - Standalone CLI tool to export Telegram chat messages to files.
Uses existing Telethon session, does NOT modify assistant state.

Usage:
    python fetch_chat.py "WNDR chat" "WNDR вдох" --period 2w
    python fetch_chat.py "WNDR club" --period 1d --format json
"""
import argparse
import asyncio
import io
import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows console encoding for Cyrillic output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telethon import TelegramClient

from config import config

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch messages from Telegram chats and save to files"
    )
    parser.add_argument("chats", nargs="+", help="Chat names or identifiers")
    parser.add_argument(
        "-p", "--period", default="1w",
        help="Time period: 12h, 1d, 3d, 1w, 2w (default: 1w)"
    )
    parser.add_argument(
        "-f", "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "-o", "--output", default="data/exports",
        help="Output directory (default: data/exports)"
    )
    parser.add_argument(
        "-l", "--limit", type=int, default=200,
        help="Max messages per chat (default: 200)"
    )
    return parser.parse_args()


def parse_period(period: str) -> timedelta:
    """Parse period string like '1w', '3d', '12h' to timedelta."""
    if not period:
        return timedelta(days=7)
    try:
        num = int(period[:-1])
        unit = period[-1].lower()
        if unit == "h":
            return timedelta(hours=num)
        elif unit == "d":
            return timedelta(days=num)
        elif unit == "w":
            return timedelta(weeks=num)
        else:
            print(f"Unknown period unit '{unit}', defaulting to {num} days")
            return timedelta(days=num)
    except (ValueError, IndexError):
        print(f"Failed to parse period '{period}', defaulting to 1 week")
        return timedelta(weeks=1)


async def resolve_chat(client: TelegramClient, name: str):
    """Resolve chat name to entity by searching dialogs."""
    name_stripped = name.strip()

    # Handle @username and URLs directly
    if name_stripped.startswith(("@", "https://", "http://", "t.me/")):
        return await client.get_entity(name_stripped)

    # Search by title in dialogs
    async for dialog in client.iter_dialogs():
        if dialog.title and dialog.title.lower() == name_stripped.lower():
            return dialog.entity

    # Fallback: try as-is
    return await client.get_entity(name_stripped)


def get_sender_name(msg) -> str:
    """Extract sender display name from message."""
    if not msg.sender:
        return "Unknown"
    first = getattr(msg.sender, "first_name", None) or ""
    last = getattr(msg.sender, "last_name", None) or ""
    full = f"{first} {last}".strip()
    return full or getattr(msg.sender, "username", None) or "Unknown"


async def fetch_messages(client, entity, since: datetime, limit: int) -> list:
    """Fetch messages from entity since given date, return as list of dicts."""
    from fragments.collector import get_topic_id

    is_forum = getattr(entity, 'forum', False)
    messages = []
    # reverse=True + offset_date = go forward from `since` date (oldest first)
    async for msg in client.iter_messages(
        entity, offset_date=since, reverse=True, limit=limit
    ):
        if not (msg.text or msg.message):
            continue
        messages.append({
            "id": msg.id,
            "date": msg.date.strftime("%Y-%m-%dT%H:%M:%S") if msg.date else None,
            "sender": get_sender_name(msg),
            "sender_id": msg.sender_id,
            "text": msg.text or msg.message or "",
            "reply_to": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
            "is_forward": msg.forward is not None,
            "message_thread_id": get_topic_id(msg, chat=entity) if is_forum else None,
        })

    return messages  # already chronological (oldest first) due to reverse=True


def sanitize_filename(name: str) -> str:
    """Replace non-filesystem-safe characters."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def save_text(messages: list, chat_name: str, period: str, output_dir: Path) -> Path:
    """Save messages as human-readable text file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{sanitize_filename(chat_name)}_{date_str}_{period}.txt"
    filepath = output_dir / filename

    lines = []
    # Header
    if messages:
        first_date = messages[0]["date"][:10] if messages[0]["date"] else "?"
        last_date = messages[-1]["date"][:10] if messages[-1]["date"] else "?"
        lines.append(f"=== {chat_name} ===")
        lines.append(f"Period: {period} ({first_date} — {last_date})")
        lines.append(f"Messages: {len(messages)}")
        lines.append("===\n")
    else:
        lines.append(f"=== {chat_name} ===")
        lines.append(f"Period: {period}")
        lines.append("Messages: 0")
        lines.append("===\n")

    # Messages
    for msg in messages:
        dt = msg["date"]
        short_date = ""
        if dt:
            # "30.01 10:15" format
            try:
                parsed = datetime.fromisoformat(dt)
                short_date = parsed.strftime("%d.%m %H:%M")
            except ValueError:
                short_date = dt
        text = msg["text"].replace("\n", "\n    ")  # indent continuations
        lines.append(f"[{short_date}] {msg['sender']}: {text}")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def save_json(messages: list, chat_name: str, period: str, output_dir: Path) -> Path:
    """Save messages as JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{sanitize_filename(chat_name)}_{date_str}_{period}.json"
    filepath = output_dir / filename

    data = {
        "chat_name": chat_name,
        "period": period,
        "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "message_count": len(messages),
        "messages": messages,
    }

    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return filepath


async def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    client = TelegramClient(
        config["session_name"], config["api_id"], config["api_hash"]
    )

    await client.connect()
    if not await client.is_user_authorized():
        print(
            "ERROR: Session not authorized. Run main.py first to create a session.",
            file=sys.stderr,
        )
        await client.disconnect()
        sys.exit(1)

    delta = parse_period(args.period)
    since = datetime.now() - delta
    output_dir = Path(args.output)
    saved_files = []

    try:
        for chat_name in args.chats:
            print(f"\n--- {chat_name} ---")
            try:
                print(f"  Resolving chat...")
                entity = await resolve_chat(client, chat_name)
                print(f"  Fetching messages (period: {args.period}, limit: {args.limit})...")
                messages = await fetch_messages(client, entity, since, args.limit)
                print(f"  Found {len(messages)} messages")

                if args.format == "json":
                    filepath = save_json(messages, chat_name, args.period, output_dir)
                else:
                    filepath = save_text(messages, chat_name, args.period, output_dir)

                print(f"  Saved: {filepath}")
                saved_files.append(str(filepath))

            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)

    finally:
        await client.disconnect()

    # Summary for Claude Code
    if saved_files:
        print(f"\n=== Done! Files saved ===")
        for f in saved_files:
            print(f"  {f}")


if __name__ == "__main__":
    asyncio.run(main())
