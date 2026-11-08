# Urgent notifications and household config

Discord has no "urgent" notification level. A low doorbell battery or an alarm that failed to arm
looks the same on a phone as a news digest. This setup gives the bot one convention for urgent
things, plus a single config file for everyone's Discord IDs so scripts don't hard-code them.

- **Urgent = a DM to the person it concerns, starting with 🚨.** Everything else stays in channels
  and threads and never uses 🚨, so the emoji keeps its meaning.
- **Scripts send urgent DMs only through `urgent_dm()`**, which adds the 🚨 itself. A script can't
  forget it, and the bot doesn't have to remember it when it writes a new script.
- **IDs live in `~/.hermes/household.toml`**, read through `household.py`. Sharing the scripts
  means sharing no one's IDs.

| File | What it is |
|------|------------|
| [`notify/notify.py`](../notify/notify.py) | `urgent_dm(person, text)` and a CLI (`notify.py urgent <person> "<text>" [--dry-run]`) |
| [`notify/household.py`](../notify/household.py) | Loads and validates the household config: `mention()`, `discord_id()`, `channel()`, `thread()`, `person_for_discord_id()` |
| [`notify/test_notify.py`](../notify/test_notify.py) | Unit tests (stdlib only) against the example config |
| [`examples/household.example.toml`](../examples/household.example.toml) | Config template with placeholder IDs |
| [`examples/SOUL-urgent.md`](../examples/SOUL-urgent.md) | SOUL.md snippet that teaches the bot the convention |

## What `urgent_dm()` does

- Prepends the real 🚨 (U+1F6A8). Bot messages sent through the Discord API don't convert the
  `:rotating_light:` shortcode, so it would show up as text; a leading shortcode or extra 🚨 is
  removed.
- Splits long text the way Hermes splits Discord replies: at most 2000 characters per message, cut
  at a newline (or a space), code blocks closed and reopened across the cut, `(1/3)` markers. Each
  part starts with 🚨, because each part is its own phone notification.
- Retries on Discord rate limits. Raises on any other error, or on an unknown person, so a failed
  alert is never silent; a failure partway through says how many parts already went out.
- Reads the bot token from `DISCORD_BOT_TOKEN` in the environment or `~/.hermes/.env`.

## Setup

Requires Python 3.11+ (`tomllib`) and no other packages.

```bash
cp notify/notify.py notify/household.py ~/.hermes/scripts/
cp examples/household.example.toml ~/.hermes/household.toml && chmod 600 ~/.hermes/household.toml
$EDITOR ~/.hermes/household.toml            # real Discord IDs
python3 ~/.hermes/scripts/household.py      # validates and prints a summary
python3 ~/.hermes/scripts/notify.py urgent alice "Test" --dry-run
```

Then append [`examples/SOUL-urgent.md`](../examples/SOUL-urgent.md) to the bot's `SOUL.md` and start
a new session. `HOUSEHOLD_CONFIG=/path/to/file.toml` points the scripts at a different config.

Using it from a script in `~/.hermes/scripts/`:

```python
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import urgent_dm

urgent_dm("alice", "**Front Door doorbell battery 8%** - charge it today.")
```

In a Hermes `no_agent` cron job, the script's stdout is still posted to the job's `deliver`
channel. For an urgent-only alert, call `urgent_dm()` and print nothing. Printing a channel message
only when the DM raises is a good fallback.

Run the tests with `python3 -I notify/test_notify.py`.
