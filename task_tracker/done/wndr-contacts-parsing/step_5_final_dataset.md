# Step 5: Structure and save final dataset

> Status: pending

## Task

Combine participants, intros, and links into one clean JSON.

## Output format

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
        "tg_channels": [],
        "instagram": null,
        "linkedin": null,
        "youtube": null,
        "websites": [],
        "mentions": []
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

## Note

This step works offline — no Telegram access needed. Can be done after April 14.

## Done when

- [ ] `wndr_contacts.json` exists and is valid JSON
- [ ] All members with enriched data
- [ ] Spot-check 5-10 records manually
