"""
fetch_topics_list.py - List all forum topics in a supergroup/channel.
Outputs topic ID, name, message count, and direct link.

Usage:
    python fetch_topics_list.py "WNDR chat"
    python fetch_topics_list.py "WNDR chat" --json
    python fetch_topics_list.py "WNDR chat" -o data/exports/wndr/topics.json
"""
import argparse
import asyncio
import io
import json
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telethon import TelegramClient
from telethon.tl.functions.channels import GetForumTopicsByIDRequest

from config import config


async def resolve_chat(client: TelegramClient, name: str):
    name_stripped = name.strip()
    if name_stripped.startswith(("@", "https://", "http://", "t.me/")):
        return await client.get_entity(name_stripped)
    async for dialog in client.iter_dialogs():
        if dialog.title and dialog.title.lower() == name_stripped.lower():
            return dialog.entity
    return await client.get_entity(name_stripped)


async def fetch_topics(client: TelegramClient, entity) -> list[dict]:
    """Fetch all forum topics via GetForumTopics."""
    topics = []
    offset_date = 0
    offset_id = 0
    offset_topic = 0
    limit = 100

    while True:
        result = await client(GetForumTopicsRequest(
            channel=entity,
            q="",
            offset_date=offset_date,
            offset_id=offset_id,
            offset_topic=offset_topic,
            limit=limit,
        ))

        if not result.topics:
            break

        for topic in result.topics:
            topics.append({
                "id": topic.id,
                "title": topic.title,
                "top_message": getattr(topic, "top_message", None),
            })

        if len(result.topics) < limit:
            break

        last = result.topics[-1]
        offset_topic = last.id
        offset_id = getattr(last, "top_message", 0) or 0

    return topics


def build_link(peer_id: int, topic_id: int) -> str:
    """Build t.me/c/ link from internal channel ID (strip -100 prefix)."""
    raw_id = str(peer_id)
    if raw_id.startswith("-100"):
        raw_id = raw_id[4:]
    return f"https://t.me/c/{raw_id}/{topic_id}"


async def main():
    parser = argparse.ArgumentParser(description="List forum topics of a Telegram supergroup")
    parser.add_argument("chat", help="Chat name or identifier")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", help="Save JSON to file")
    args = parser.parse_args()

    client = TelegramClient(config["session_name"], config["api_id"], config["api_hash"])
    await client.connect()
    if not await client.is_user_authorized():
        print("ERROR: Session not authorized. Run main.py first to authenticate.", file=sys.stderr)
        await client.disconnect()
        sys.exit(1)

    try:
        print(f"Resolving chat: {args.chat}", file=sys.stderr)
        entity = await resolve_chat(client, args.chat)
        chat_id = entity.id  # raw, without -100

        print(f"  Found: {getattr(entity, 'title', entity)} (id={entity.id})", file=sys.stderr)
        print("  Fetching topics...", file=sys.stderr)

        topics = await fetch_topics(client, entity)
        print(f"  Got {len(topics)} topics", file=sys.stderr)

        # Enrich with links
        full_id = int(f"-100{entity.id}")
        for t in topics:
            t["link"] = build_link(full_id, t["id"])

        if args.output:
            import pathlib
            pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(args.output).write_text(
                json.dumps({"chat": args.chat, "chat_id": full_id, "topics": topics}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"Saved to {args.output}", file=sys.stderr)

        if args.json or args.output:
            print(json.dumps(topics, ensure_ascii=False, indent=2))
        else:
            # Pretty table
            print(f"\n{'ID':<8} {'Messages':<10} {'Title':<40} Link")
            print("-" * 100)
            for t in topics:
                msg_count = t.get("top_message") or "?"
                print(f"{t['id']:<8} {str(msg_count):<10} {t['title']:<40} {t['link']}")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
