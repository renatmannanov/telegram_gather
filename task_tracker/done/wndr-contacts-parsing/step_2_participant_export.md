# Step 2: Build `fetch_contacts.py` — participant export

> Status: pending

## Task

Create `fetch_contacts.py` at project root. Export all members with bios.

## Approach

1. Try `client.get_participants(entity)` first
2. If fails (ChatAdminRequiredError) — fallback: collect unique senders from messages
3. For each user: `GetFullUserRequest` to get bio
4. Rate limit: `asyncio.sleep(0.5)` between bio requests, catch `FloodWaitError`

## Output

```json
{
  "user_id": 123456,
  "first_name": "...",
  "last_name": "...",
  "username": "...",
  "bio": "..."
}
```

Save to `data/exports/wndr/wndr_participants.json`

## Done when

- [ ] `fetch_contacts.py` exists and runs
- [ ] JSON exported with all members + bios
- [ ] FloodWait handled gracefully
