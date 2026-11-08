# housebot

Plugins and tools for a household [Hermes Agent](https://github.com/NousResearch/hermes-agent) bot
that several family members share over Discord.

| Path | What it is |
|------|------------|
| [`docs/gmail.md`](docs/gmail.md) | Read-only Gmail for the bot: architecture, setup, adding inboxes, cron allowlist, pitfalls |
| [`gmail-mcp/setup.sh`](gmail-mcp/setup.sh) | Creates the isolated `gmail-mcp` user, builds the server at a pinned commit, locks the bot's SSH key to it |
| [`hermes-gmail-guard/`](https://github.com/eisene/hermes-gmail-guard) | Hermes plugin: human approval for every Gmail read, naming the inbox and who asked; per-job cron allowlist |
| [`gmail-multi-mcp/`](https://github.com/eisene/gmail-multi-mcp) | Read-only Gmail MCP server (fork) with paginated listing, regex search, credential redaction, locked mode |
| [`docs/notify.md`](docs/notify.md) | Urgent 🚨 DMs and a central household config (Discord IDs) for the bot's scripts |
| [`notify/`](notify) | `notify.py` (`urgent_dm()`, Discord-style message splitting) and `household.py` (config loader), with tests |
| [`examples/`](examples) | Guard config, household config template and SOUL.md snippets to adapt |

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/eisene/housebot.git
```
