# Step 4: Extract social links and enrich contacts

> Status: pending

## Task

Parse social links from bios (step 2) and intro messages (step 3).

## Regex patterns

- Telegram channels: `t\.me/[a-zA-Z0-9_]+` (exclude `t.me/joinchat/`)
- Instagram: `instagram\.com/[a-zA-Z0-9_.]+`
- LinkedIn: `linkedin\.com/in/[a-zA-Z0-9_-]+`
- YouTube: `youtube\.com/@?[a-zA-Z0-9_-]+`
- Websites: general URL regex, exclude known platforms
- Telegram @mentions: `@[a-zA-Z0-9_]{5,}` (save all)

## Note

This step works offline — no Telegram access needed. Can be done after April 14.

## Done when

- [ ] Each member record has `links` object
- [ ] Links extracted from both bios and intro messages
