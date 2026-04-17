# Plan: WNDR contacts parsing

> Status: done
> Deadline: 2026-04-14 (end of WNDR season access)
> Project: telegram-gather
> Priority: HIGH (time-sensitive)

## Context

Renat is leaving WNDR community after 2 seasons (since September 2025). Access to the group chat ends ~April 14, 2026. Need to extract contacts and context about people before losing access.

## Goal

Parse WNDR Telegram group to save:
- Member profiles (name, username, bio, links to their TG channels/Instagram/etc)
- Introduction messages ("знакомство") — self-descriptions people posted when joining
- Extract social links from bios and messages (TG channels, Instagram, websites)

This data will be used later for wndrverse (passive networking tool) and personal ayda_friends network.

## Tool

`telegram-gather` — existing Telethon userbot. Has `fetch_chat.py` CLI that already supports WNDR groups. Can read any chat where the account is a member.

### What already exists

- `fetch_chat.py` — exports messages to text/json. Supports `--period`, `--limit`, `--format`. Already used with WNDR groups (exports from Feb 2026 exist in `data/exports/`)
- `scripts/bulk_collect.py` — bulk message collection into PostgreSQL (fragments). NOT needed here — we want a standalone export, not DB ingestion
- Telethon session is set up and authorized

### What needs to be built

- **Participant export** — `get_participants()` + `get_full_user()` for bios. Nothing like this exists in the project
- **Introduction message detection** — filtering by hashtag/thread/topic. `fetch_chat.py` has no topic/thread support
- **Social link extraction** — regex parsing of t.me, instagram, website links from text

## Architecture decision

**New standalone script `fetch_contacts.py`** at project root (next to `fetch_chat.py`).

Rationale:
- `fetch_chat.py` is a message export tool — adding participant logic would bloat its scope
- Same pattern: standalone CLI, uses existing Telethon session via `config.py`, saves to `data/exports/`
- No DB dependency (unlike `scripts/bulk_collect.py`)
- Can reuse `resolve_chat()` and session setup pattern from `fetch_chat.py`

Do NOT refactor `fetch_chat.py` or create a shared module — the scripts are simple enough to have some duplication. Extract shared utils only if a third script appears.

## Steps

| # | Step | Status | Depends |
|---|------|--------|---------|
| 1 | Identify WNDR groups and threads | done | — |
| 2 | Build `fetch_contacts.py` — participant export | done | 1 |
| 3 | Export introduction messages | done | 1 |
| 4 | Extract social links and enrich contacts | done | 2, 3 |
| 5 | Structure and save final dataset | done | 4 |
| 6 | Completion checklist | done | 5 |

## Step details

### Step 1: Identify WNDR groups and threads

Target group: **"WNDR chat"** (the main group). Other WNDR groups (вдох, club) are not needed.

**Confirmed:** the group is a forum (topics/threads). Need to identify which topic contains introductions.

**Action:** user provides topic names and descriptions. Record chat ID + intro topic ID.

**Done when:** chat ID + intro topic ID recorded

### Step 2: Build `fetch_contacts.py` — participant export

Create `fetch_contacts.py` in project root. CLI interface:

```
python fetch_contacts.py "WNDR chat" --format json --output data/exports/wndr
```

Logic:
1. Resolve chat via dialog search (same as `fetch_chat.py`)
2. `client.get_participants(entity)` — get all members
3. For each member: `client(GetFullUserRequest(user))` to get bio
4. Save as JSON

**Rate limiting:** `get_full_user()` triggers Telethon FloodWait if called too fast. Add `asyncio.sleep(0.5)` between calls (or catch `FloodWaitError` and sleep for the requested time). For ~100-200 members this means ~1-2 minutes total.

**Fallback if `get_participants()` fails (no admin rights):**
1. Fetch all messages from the chat (or at least the intro topic)
2. Collect unique senders → set of user_id + name + username
3. Then call `GetFullUserRequest` for each user to get bio
This is slower but works without admin rights.

**Output per member:**
```json
{
  "user_id": 123456,
  "first_name": "...",
  "last_name": "...",
  "username": "...",
  "bio": "..."
}
```

**Done when:** script runs, exports JSON with all members + bios from "WNDR chat"

### Step 3: Export introduction messages

Use `fetch_chat.py` or extend `fetch_contacts.py` to find introduction messages.

**Strategy (try in order):**
1. If chat is a forum — find the "знакомство" topic, fetch all messages from it
2. If not a forum — search for messages with `#знакомство` hashtag
3. Fallback — search for messages containing keywords: "меня зовут", "привет, я", "обо мне"

**Important:** Default `--limit 200` is not enough. Introduction messages span the entire chat history. Use `--limit 0` (no limit) or a high number like `--limit 5000`. Adjust `--period` to cover the full WNDR season (~6 months, use `26w` or add an `--all` flag).

**Output:** Array of `{user_id, sender_name, text, date, message_id}` — attributed to users so they can be joined with step 2 data.

**Done when:** JSON file with introduction messages, each linked to a user_id

### Step 4: Extract social links and enrich contacts

Parse social links from two sources:
1. Member bios (from step 2)
2. Introduction messages (from step 3)

**Regex patterns:**
- Telegram channels: `t\.me/[a-zA-Z0-9_]+` (exclude `t.me/joinchat/` invite links)
- Instagram: `instagram\.com/[a-zA-Z0-9_.]+`
- LinkedIn: `linkedin\.com/in/[a-zA-Z0-9_-]+`
- YouTube: `youtube\.com/@?[a-zA-Z0-9_-]+`
- Websites: general URL regex, exclude telegram/instagram/linkedin/youtube/known platforms
- Telegram @mentions: `@[a-zA-Z0-9_]{5,}` (save all, filter later)

**Done when:** each member record has a `links` object with extracted social links

### Step 5: Structure and save final dataset

Combine everything into a clean dataset:
```json
{
  "members": [
    {
      "user_id": 123,
      "name": "...",
      "username": "...",
      "bio": "...",
      "introduction": "...",
      "links": {
        "tg_channels": ["t.me/..."],
        "instagram": "...",
        "websites": ["..."]
      },
      "source_group": "WNDR chat"
    }
  ],
  "metadata": {
    "parsed_at": "2026-04-XX",
    "source_group": "WNDR chat",
    "total_members": 100
  }
}
```

Save to `data/exports/wndr/wndr_contacts.json`

**Done when:** file exists, valid JSON, contains all members with enriched data

### Step 6: Completion checklist

See `step_6_completion.md`

## Notes

- This is a one-time extraction, not ongoing
- Only public info: bios + messages people voluntarily posted in the group
- The script and plan both live in telegram-gather
- After extraction, data feeds into wndrverse MVP
- `fetch_contacts.py` stays in telegram-gather as a reusable tool — it's generic enough for any chat, not WNDR-specific
- Existing `data/exports/WNDR*_2026-02-06_*` files are old message exports, not contacts — don't delete them
