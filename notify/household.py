#!/usr/bin/env python3
"""Household settings for the bot's scripts: people, Discord IDs, channels, threads.

All IDs live in one TOML file (default ~/.hermes/household.toml, override with
$HOUSEHOLD_CONFIG), so scripts never hard-code them and the code can be shared
without anyone's IDs in it. No secrets here: tokens stay in ~/.hermes/.env.

    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import household as hh
    hh.mention("alice")             # "<@111111111111111111>"
    hh.discord_id("bob")            # "222222222222222222"
    hh.channel("general")           # "333333333333333333"
    hh.thread("bob-reminders")      # ("333333333333333333", "555555555555555555")

`python3 household.py` validates the file and prints a summary.
"""
import os
import sys
import tomllib
from pathlib import Path

DEFAULT_PATH = Path.home() / ".hermes" / "household.toml"
_cache: dict | None = None


class ConfigError(RuntimeError):
    pass


def config_path() -> Path:
    return Path(os.environ.get("HOUSEHOLD_CONFIG") or DEFAULT_PATH).expanduser()


def _snowflake(value, where: str) -> str:
    s = str(value).strip()
    if not s.isdigit() or not 15 <= len(s) <= 21:
        raise ConfigError(f"{config_path()}: {where} = {value!r} is not a Discord ID")
    return s


def _validate(cfg: dict) -> dict:
    people = cfg.get("people") or {}
    if not isinstance(people, dict):
        raise ConfigError(f"{config_path()}: [people] must be a table")
    for key, p in people.items():
        if key != key.lower():
            raise ConfigError(f"{config_path()}: person key {key!r} must be lowercase")
        p.setdefault("name", key.capitalize())
        if "discord_id" in p:
            p["discord_id"] = _snowflake(p["discord_id"], f"people.{key}.discord_id")
        p["other_discord_ids"] = [
            _snowflake(v, f"people.{key}.other_discord_ids")
            for v in p.get("other_discord_ids", [])
        ]
    chans = cfg.setdefault("channels", {})
    for name, cid in chans.items():
        chans[name] = _snowflake(cid, f"channels.{name}")
    threads = cfg.setdefault("threads", {})
    for name, t in threads.items():
        if t.get("channel") not in chans:
            raise ConfigError(f"{config_path()}: threads.{name}.channel must name a [channels] entry")
        t["id"] = _snowflake(t.get("id"), f"threads.{name}.id")
    return cfg


def load(reload: bool = False) -> dict:
    global _cache
    if _cache is None or reload:
        path = config_path()
        try:
            with path.open("rb") as f:
                _cache = _validate(tomllib.load(f))
        except FileNotFoundError:
            raise ConfigError(f"Household config not found: {path}") from None
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from None
    return _cache


def people() -> dict[str, dict]:
    return load().get("people", {})


def person(key: str) -> dict:
    k = key.strip().lower()
    p = people().get(k)
    if p is None:
        raise ConfigError(f"No person {key!r} in {config_path()}; known: {', '.join(people())}")
    return p


def discord_id(key: str) -> str:
    """The Discord account that gets this person's pings and DMs."""
    p = person(key)
    if "discord_id" not in p:
        raise ConfigError(f"{p['name']} has no discord_id in {config_path()}")
    return p["discord_id"]


def mention(key: str) -> str:
    return f"<@{discord_id(key)}>"


def person_for_discord_id(uid: str) -> str | None:
    """Map any of a person's Discord accounts back to their key."""
    uid = str(uid)
    for k, p in people().items():
        if uid == p.get("discord_id") or uid in p["other_discord_ids"]:
            return k
    return None


def channel(name: str) -> str:
    chans = load()["channels"]
    if name not in chans:
        raise ConfigError(f"No channel {name!r} in {config_path()}; known: {', '.join(chans)}")
    return chans[name]


def thread(name: str) -> tuple[str, str]:
    """(parent channel ID, thread ID)."""
    threads = load()["threads"]
    if name not in threads:
        raise ConfigError(f"No thread {name!r} in {config_path()}; known: {', '.join(threads)}")
    t = threads[name]
    return channel(t["channel"]), t["id"]


def main() -> int:
    try:
        cfg = load()
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"{config_path()} OK")
    for k, p in cfg.get("people", {}).items():
        print(f"  person  {k:<18} {p['name']:<12} {p.get('discord_id', '(no Discord)')}")
    for n, c in cfg["channels"].items():
        print(f"  channel {n:<18} {c}")
    for n, t in cfg["threads"].items():
        print(f"  thread  {n:<18} {t['id']} in #{t['channel']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
