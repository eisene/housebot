## Urgent notifications
Discord has no "urgent" alert level, so urgent things go as a Discord DM that starts with 🚨.
- Urgent means it needs action soon: safety, security, or something that breaks if ignored (a doorbell or sensor about to die, the alarm failing to arm). Send it only to the person it concerns. If that person has no Discord, tell another adult in the household instead.
- Everything else goes in channels or threads as usual and never uses 🚨, so the emoji keeps its meaning.
- Send the real 🚨 character, never the text ":rotating_light:" (Discord does not convert shortcodes in bot messages).
- In scripts and cron jobs, send urgent DMs only with urgent_dm(person, text) from ~/.hermes/scripts/notify.py, which adds the 🚨 itself. Never call the Discord API directly for them. From a turn: python3 ~/.hermes/scripts/notify.py urgent <person> "<text>" (add --dry-run to preview).
- Discord IDs of people, channels and threads live only in ~/.hermes/household.toml (read it with ~/.hermes/scripts/household.py). New scripts look IDs up there instead of hard-coding them; the admin edits the file when someone joins or an ID changes.
