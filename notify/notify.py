#!/usr/bin/env python3
"""Notification helpers for the family bot's scripts.

Urgent = needs action soon (safety, security, or something that breaks if ignored).
Urgent notifications go as a Discord DM to the affected person and start with 🚨.
Everything else goes in channels/threads and never uses 🚨, so the alert keeps its meaning.

In a script:
    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from notify import urgent_dm
    urgent_dm("alice", "**Front Door doorbell battery at 8%** - charge it today.")

From a shell / an agent turn:
    python3 ~/.hermes/scripts/notify.py urgent alice "text"
    python3 ~/.hermes/scripts/notify.py urgent alice "text" --dry-run   # print, don't send

People and their Discord IDs come from the household config (see household.py).
urgent_dm() adds the 🚨 itself (the real U+1F6A8 character; Discord does not turn the
text ":rotating_light:" into an emoji when a bot posts through the API) and splits long
messages the way Hermes does for Discord: at most 2000 characters per message, cut at a
newline or space, code blocks closed and reopened across the cut, "(1/3)" markers.
Every part starts with 🚨, since each part is its own phone notification.
Never call the Discord API directly for urgent DMs; always go through this module.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import household  # noqa: E402

URGENT = "\U0001F6A8"  # 🚨
URGENT_PREFIX = URGENT + " "
DISCORD_LIMIT = 2000
API = "https://discord.com/api/v10"
SUPPRESS_EMBEDS = 1 << 2
FENCE_CLOSE = "\n```"
INDICATOR_RESERVE = 10  # room for " (NN/NN)"

_dm_channels: dict[str, str] = {}
_token: str | None = None


# ---------- splitting (port of Hermes BasePlatformAdapter.truncate_message) ----------
def _fence_state(text: str, in_code: bool, lang: str) -> tuple[bool, str]:
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            tag = s[3:].split()
            in_code, lang = (False, "") if in_code else (True, tag[0] if tag else "")
    return in_code, lang


def _inline_ticks(text: str) -> int:
    """Unescaped backticks outside fence-marker lines (fences don't open inline spans)."""
    n = 0
    for line in text.split("\n"):
        if not line.strip().startswith("```"):
            n += line.count("`") - line.count("\\`")
    return n


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Split `text` into Discord-sized parts, each at most `limit` characters."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    carry: str | None = None  # language tag when the previous part ended inside a fence
    while rest:
        prefix = f"```{carry}\n" if carry is not None else ""
        if len(prefix) + len(rest) <= limit - INDICATOR_RESERVE:
            final = prefix + rest
            if carry is not None and _fence_state(rest, True, carry)[0]:
                final += FENCE_CLOSE
            chunks.append(final)
            break
        room = max(1, limit - INDICATOR_RESERVE - len(prefix) - len(FENCE_CLOSE))
        region = rest[:room]
        cut = region.rfind("\n")
        if cut < room // 2:
            cut = region.rfind(" ")
        if cut < 1:
            cut = room  # one huge word: hard cut
        # Don't cut inside an inline `code span`.
        if _inline_ticks(rest[:cut]) % 2:
            bt = rest.rfind("`", 0, cut)
            safe = max(rest.rfind(" ", 0, bt), rest.rfind("\n", 0, bt))
            if safe > room // 4:
                cut = safe
        body = rest[:cut]
        # Drop exactly the separator we cut at; keep indentation of the next line.
        rest = rest[cut + 1:] if rest[cut:cut + 1] in ("\n", " ") else rest[cut:]
        in_code, lang = _fence_state(body, carry is not None, carry or "")
        chunks.append(prefix + body + (FENCE_CLOSE if in_code else ""))
        carry = lang if in_code else None
    chunks = [c for c in chunks if c.strip()]
    if len(chunks) > 1:
        chunks = [f"{c} ({i}/{len(chunks)})" for i, c in enumerate(chunks, 1)]
    return chunks


def urgent_text(text: str) -> str:
    """The text urgent_dm() sends, before splitting: one 🚨 prefix, shortcode normalised."""
    t = text.strip()
    while True:  # drop any leading 🚨 / :rotating_light:, however many
        for prefix in (URGENT, ":rotating_light:"):
            if t.startswith(prefix):
                t = t[len(prefix):].lstrip()
                break
        else:
            return URGENT_PREFIX + t


def urgent_parts(text: str) -> list[str]:
    """The exact messages urgent_dm() sends, in order, each starting with 🚨."""
    body = urgent_text(text)[len(URGENT_PREFIX):]
    return [URGENT_PREFIX + p for p in split_message(body, DISCORD_LIMIT - len(URGENT_PREFIX))]


# ---------- Discord REST ----------
def _get_token() -> str:
    global _token
    if _token:
        return _token
    tok = os.environ.get("DISCORD_BOT_TOKEN")
    if not tok:
        env = Path.home() / ".hermes" / ".env"
        for line in env.read_text().splitlines() if env.exists() else []:
            if line.strip().startswith("DISCORD_BOT_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not tok:
        raise RuntimeError("DISCORD_BOT_TOKEN not found")
    _token = tok
    return tok


def _api(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(5):
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bot {_get_token()}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (housebot-notify, 1.1)",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(json.loads(e.read() or b"{}").get("retry_after", 2)) + 0.5)
                continue
            raise RuntimeError(f"Discord {method} {path} -> {e.code}: {e.read()[:300]!r}") from None
    raise RuntimeError(f"Discord {method} {path}: rate limited repeatedly")


def urgent_dm(person: str, text: str, *, dry_run: bool = False) -> list[str]:
    """DM `person` (a key in the household config) an urgent message starting with 🚨.

    Long text is split into several DMs (see split_message). Returns the sent message IDs.
    Raises on an unknown person or a Discord error, so a failed alert is never silent;
    if a later part fails, the error says how many parts already went out.
    """
    key = person.strip().lower()
    uid = household.discord_id(key)
    parts = urgent_parts(text)
    if dry_run:
        for i, p in enumerate(parts, 1):
            print(f"[dry-run] DM {key} ({uid}) part {i}/{len(parts)}, {len(p)} chars:\n{p}")
        return []
    if uid not in _dm_channels:
        _dm_channels[uid] = _api("POST", "/users/@me/channels", {"recipient_id": uid})["id"]
    sent: list[str] = []
    for p in parts:
        try:
            msg = _api("POST", f"/channels/{_dm_channels[uid]}/messages",
                       {"content": p, "flags": SUPPRESS_EMBEDS})
        except RuntimeError as e:
            raise RuntimeError(f"{e} (after {len(sent)} of {len(parts)} parts were sent)") from None
        sent.append(msg["id"])
    return sent


def main(argv=None):
    p = argparse.ArgumentParser(description="Family bot notifications")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("urgent", help="send an urgent 🚨 DM to one person")
    u.add_argument("person", help="person key from the household config")
    u.add_argument("text", help="message text; use - to read it from stdin")
    u.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    text = sys.stdin.read() if a.text == "-" else a.text
    try:
        ids = urgent_dm(a.person, text, dry_run=a.dry_run)
    except (household.ConfigError, RuntimeError) as e:
        sys.exit(f"error: {e}")
    if ids:
        print(f"sent {a.person} {len(ids)} message(s): {', '.join(ids)}")


if __name__ == "__main__":
    main()
