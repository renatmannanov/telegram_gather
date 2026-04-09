# Step 3: Export introduction messages

> Status: pending

## Task

Fetch introduction messages from the WNDR chat intro topic.

## Strategy

1. **Primary (forum):** fetch all messages from the intro topic via `reply_to` filter
2. **Fallback:** search `#знакомство` via `client.iter_messages(entity, search='#знакомство')`
3. **Last resort:** keyword search: "меня зовут", "привет, я", "обо мне"

## Important

- Use high limit (no cap or 5000+) — intros span entire chat history
- Each message must be attributed to user_id for joining with step 2

## Output

Array of `{user_id, sender_name, username, text, date, message_id}`

Save to `data/exports/wndr/wndr_topic_intro.json`

## Done when

- [ ] JSON file with introduction messages exists
- [ ] Each message linked to user_id
- [ ] Covers full chat history (not just recent)
