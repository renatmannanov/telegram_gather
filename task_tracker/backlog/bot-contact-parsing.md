# Backlog: Bot-driven contact parsing

## Idea

Add bot commands to parse any group/channel on demand:
- `/parse "Group Name"` — fetch participants + bios + topic messages
- `/parse_status` — show progress
- Save results to PostgreSQL (not JSON files)
- `/who дизайнер` — search contacts by keywords in bio/intro/offerings

## Why

Current scripts (fetch_contacts.py, fetch_topic.py, build_contacts.py) work as local CLI tools.
Moving this to the bot enables:
- Parsing from prod (Railway) without local session
- Persistent storage in shared DB (accessible by ayda_think)
- Querying contacts via bot interface

## Architecture sketch

### New DB tables
- `contacts` — user_id, name, username, bio, source_group
- `contact_messages` — user_id, source_group, topic, text, date, message_id
- `contact_links` — user_id, platform, handle/url

### Bot commands
- `/parse "Group" [--topics intro,requests]` — runs parsing as background task (like /collect)
- `/parse_status` — shows progress
- `/who <query>` — keyword search across bio + intro + offerings
- `/contacts <group>` — list parsed contacts for a group

### Reuse
- Core logic from fetch_contacts.py, fetch_topic.py, build_contacts.py
- Same rate limiting, FloodWait handling
- Same link extraction regexes

## Dependencies

- fragments module pattern (background tasks, /collect commands)
- PostgreSQL (already shared with ayda_think)

## Priority

Low — nice to have, not urgent. Current CLI scripts cover immediate needs.
