"""
build_contacts.py - Combine participants, topics, and links into final wndr_contacts.json.
Runs fully offline — no Telegram access needed.

Usage:
    python build_contacts.py --input data/exports/wndr --output data/exports/wndr/wndr_contacts.json
"""
import argparse
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# --- Link extraction ---

# Patterns to extract
LINK_PATTERNS = {
    "tg_channels": re.compile(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{5,})', re.IGNORECASE),
    "instagram": re.compile(r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)', re.IGNORECASE),
    "linkedin": re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+)', re.IGNORECASE),
    "youtube": re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/@?([a-zA-Z0-9_-]+)', re.IGNORECASE),
}

WEBSITE_PATTERN = re.compile(r'https?://[^\s<>\"\')]+', re.IGNORECASE)

# Telegram links to exclude
TG_EXCLUDE = re.compile(r't\.me/(joinchat|c|\+)', re.IGNORECASE)
# Known platforms to exclude from "websites"
KNOWN_PLATFORMS = re.compile(
    r'(t\.me|telegram\.|instagram\.com|linkedin\.com|youtube\.com|youtu\.be|'
    r'wa\.me|whatsapp\.com|facebook\.com|fb\.com|tiktok\.com|twitter\.com|x\.com)',
    re.IGNORECASE
)
MENTION_PATTERN = re.compile(r'(?<!\w)@([a-zA-Z0-9_]{5,})')


def extract_links(text: str) -> dict:
    """Extract social links from text."""
    links = {
        "tg_channels": [],
        "instagram": [],
        "linkedin": [],
        "youtube": [],
        "websites": [],
        "mentions": [],
    }

    for category, pattern in LINK_PATTERNS.items():
        for match in pattern.finditer(text):
            full = match.group(0)
            handle = match.group(1)
            if category == "tg_channels" and TG_EXCLUDE.search(full):
                continue
            if handle not in links[category]:
                links[category].append(handle)

    # Websites (exclude known platforms)
    for match in WEBSITE_PATTERN.finditer(text):
        url = match.group(0).rstrip('.,;:!?)')
        if not KNOWN_PLATFORMS.search(url):
            if url not in links["websites"]:
                links["websites"].append(url)

    # @mentions
    for match in MENTION_PATTERN.finditer(text):
        mention = match.group(1)
        # Exclude if it's already captured as a tg_channel
        if mention not in links["mentions"] and mention not in links["tg_channels"]:
            links["mentions"].append(mention)

    return links


def merge_links(base: dict, new: dict):
    """Merge new links into base, avoiding duplicates."""
    for key in base:
        for item in new.get(key, []):
            if item not in base[key]:
                base[key].append(item)


# --- Data loading ---

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CHAT_LINK_PREFIX = "https://t.me/c/2924475859"


def make_message_entry(msg: dict) -> dict:
    """Convert a raw message dict to {text, date, url}."""
    return {
        "text": msg["text"],
        "date": msg.get("date"),
        "url": f"{CHAT_LINK_PREFIX}/{msg['id']}",
    }


def collect_user_texts_from_topic(topic_data: dict, only_roots=False) -> dict:
    """Collect message entries per user_id from a topic file.

    If only_roots=False, also includes replies where the author matches the root author.
    Returns {user_id: [{text, date, url}, ...]}
    """
    user_entries = {}
    for thread in topic_data.get("threads", []):
        root = thread.get("root")
        if not root:
            continue
        uid = root.get("user_id")
        if uid:
            user_entries.setdefault(uid, []).append(make_message_entry(root))

        if not only_roots:
            for reply in thread.get("replies", []):
                if reply.get("user_id") == uid:
                    user_entries.setdefault(uid, []).append(make_message_entry(reply))

    return user_entries


def collect_root_texts_by_user(topic_data: dict) -> dict:
    """Collect only root message entries per user_id."""
    user_entries = {}
    for thread in topic_data.get("threads", []):
        root = thread.get("root")
        if not root:
            continue
        uid = root.get("user_id")
        if uid:
            user_entries.setdefault(uid, []).append(make_message_entry(root))
    return user_entries


def parse_args():
    parser = argparse.ArgumentParser(description="Build final WNDR contacts dataset")
    parser.add_argument("-i", "--input", default="data/exports/wndr", help="Input directory")
    parser.add_argument("-o", "--output", default="data/exports/wndr/wndr_contacts.json", help="Output file")
    return parser.parse_args()


def main():
    args = parse_args()
    input_dir = Path(args.input)

    # Load participants
    participants_data = load_json(input_dir / "wndr_participants.json")
    participants = participants_data["participants"]
    print(f"Loaded {len(participants)} participants")

    # Load topics
    topics = {}
    topic_files = {
        "intro": "wndr_topic_intro.json",
        "requests": "wndr_topic_requests.json",
        "offerings": "wndr_topic_offerings.json",
        "sales": "wndr_topic_sales.json",
    }
    for name, filename in topic_files.items():
        path = input_dir / filename
        if path.exists():
            topics[name] = load_json(path)
            print(f"Loaded {name}: {topics[name]['total_messages']} messages, {topics[name]['total_threads']} threads")
        else:
            print(f"Skipping {name}: {path} not found")

    # Collect texts per user from each topic
    # Intro: root + self-replies (person adds to their own intro)
    intro_texts = collect_user_texts_from_topic(topics.get("intro", {}), only_roots=False) if "intro" in topics else {}
    # Requests/offerings/sales: only root messages
    requests_texts = collect_root_texts_by_user(topics.get("requests", {})) if "requests" in topics else {}
    offerings_texts = collect_root_texts_by_user(topics.get("offerings", {})) if "offerings" in topics else {}
    sales_texts = collect_root_texts_by_user(topics.get("sales", {})) if "sales" in topics else {}

    # Build contacts
    contacts = []
    for p in participants:
        uid = p["user_id"]
        name = f"{p['first_name']} {p['last_name']}".strip()

        # Combine intro entries
        intro_entries = intro_texts.get(uid, [])
        introduction = "\n\n".join(e["text"] for e in intro_entries) if intro_entries else ""

        # Collect requests/offerings/sales entries
        user_requests = requests_texts.get(uid, [])
        user_offerings = offerings_texts.get(uid, [])
        user_sales = sales_texts.get(uid, [])

        # Extract links from all sources
        links = {"tg_channels": [], "instagram": [], "linkedin": [], "youtube": [], "websites": [], "mentions": []}

        # 1. Bio links
        bio = p.get("bio", "")
        if bio:
            merge_links(links, extract_links(bio))

        # 2. Intro links
        for entry in intro_entries:
            merge_links(links, extract_links(entry["text"]))

        # 3. Requests/offerings/sales links (from their own posts)
        for entry in user_requests + user_offerings + user_sales:
            merge_links(links, extract_links(entry["text"]))

        contact = {
            "user_id": uid,
            "name": name,
            "username": p.get("username"),
            "bio": bio,
            "introduction": introduction,
            "links": links,
            "requests": user_requests,
            "offerings": user_offerings,
            "sales": user_sales,
            "source_group": "WNDR chat",
        }
        contacts.append(contact)

    # Stats
    with_intro = sum(1 for c in contacts if c["introduction"])
    with_links = sum(1 for c in contacts if any(c["links"][k] for k in c["links"]))
    with_requests = sum(1 for c in contacts if c["requests"])
    with_offerings = sum(1 for c in contacts if c["offerings"])
    with_sales = sum(1 for c in contacts if c["sales"])

    print(f"\n--- Stats ---")
    print(f"Total contacts: {len(contacts)}")
    print(f"With intro: {with_intro}")
    print(f"With links: {with_links}")
    print(f"With requests: {with_requests}")
    print(f"With offerings: {with_offerings}")
    print(f"With sales: {with_sales}")

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "metadata": {
            "parsed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "source_group": "WNDR chat",
            "total_members": len(contacts),
            "with_intro": with_intro,
            "with_links": with_links,
            "with_requests": with_requests,
            "with_offerings": with_offerings,
            "with_sales": with_sales,
        },
        "members": contacts,
    }

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
