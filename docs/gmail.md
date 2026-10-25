# Read-only Gmail for a shared household bot

This lets a [Hermes](https://github.com/NousResearch/hermes-agent) bot that several family members
share over Discord search and read their Gmail, while keeping their credentials out of the bot's
reach.

## How it fits together

```
Discord ──> Hermes (bot user)
              │  gmail-guard plugin: approval card per read, names the inbox and who asked
              │
              └─ ssh -T gmail-mcp@localhost   (key limited to one forced command)
                     │
                     └─ gmail-multi-mcp, locked mode   (separate Unix user, home 0700)
                            OAuth gmail.readonly tokens · redaction · untrusted-content fencing
```

| Layer | What it enforces | Who enforces it |
|-------|------------------|-----------------|
| OAuth scope `gmail.readonly` | No sending, deleting or changing mail, even with a stolen token | Google |
| Separate Unix user `gmail-mcp` | The bot can't read the tokens or modify the server | The OS |
| SSH forced command (`restrict,command=…`) | The bot's key can only start the server: no shell, pty or forwarding | sshd |
| Locked mode (`GMAIL_MCP_LOCKED=1`) | Only 7 read tools exist; no setup, connect or write tools | Server |
| Redaction | Sign-in codes, reset/login links, temporary passwords and API keys are removed before the bot sees them | Server |
| Fencing | Mail is wrapped in a labelled, nonce-delimited "untrusted data" block | Server |
| [gmail-guard](../hermes-gmail-guard) | A human approves each read (per inbox); cron jobs need a root-owned allowlist | Hermes plugin |

The approval card isn't a hard boundary: a bot with a shell could talk to the server directly. It's
there to catch crossed wires ("why is it searching *my* inbox?") and to make every access visible.
The layers above it hold either way.

The server is [eisene/gmail-multi-mcp](https://github.com/eisene/gmail-multi-mcp), a fork of
[dtaveeva/gmail-multi-mcp](https://github.com/dtaveeva/gmail-multi-mcp) that adds paginated
`gmail_list`, regex `gmail_grep`, redaction and locked mode.

## Setup

### 1. Google Cloud (once, about 10 minutes)
1. Create a project and enable the **Gmail API**.
2. **Google Auth Platform → Branding:** set the app name and contact emails. Placeholder homepage and
   privacy URLs are fine, because nobody reviews an app that isn't submitted for verification.
3. **Audience:** choose External, then **Publish app** so it shows *In production*. In *Testing*,
   refresh tokens expire after 7 days. Ignore the "verification required" warnings; unverified
   apps are limited to 100 users and show a warning screen at sign-in.
4. **Data Access:** add only `https://www.googleapis.com/auth/gmail.readonly`.
5. **Clients → Create client → Desktop app.** Optionally tick "Use this client with an AI-powered
   agent". It's only a label, and it's required if you later move to Google's hosted Gmail MCP.
   Download the JSON.

One project serves the whole household. Each person authorizes it for their own account only, and
owning the project gives you no access to anyone's mail.

### 2. Server user (once, with sudo)
1. Download a Node release and verify it (`SHASUMS256.txt` signature plus checksum). Use the
   latest security release.
2. On the bot user, create a key: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/gmail_mcp_ed25519`.
3. Put `oauth-client.json` and the bot's `.pub` (as `bot.pub`) in `~/gmail-mcp-staging/` of the
   admin user.
4. Read [`gmail-mcp/setup.sh`](../gmail-mcp/setup.sh), then run `sudo ./setup.sh`. Settings
   (commit, Node tarball and sha256, timezone, paths) can be overridden from the environment.

The script creates the `gmail-mcp` user. It builds the server at a pinned commit with
`npm ci --ignore-scripts` and runs its test suite. It makes the code, Node, `bin/` and `.ssh/`
root-owned. Finally it authorizes the bot's key with a forced command that starts only the locked
server.

### 3. Wire up Hermes (as the bot user)
```bash
echo y | hermes mcp add gmail --connect-timeout 60 --command ssh --args \
  -i ~/.ssh/gmail_mcp_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
  -o ServerAliveInterval=30 -T gmail-mcp@localhost
hermes plugins install eisene/hermes-gmail-guard --enable
```
Then write the guard config (see [`examples/hermes-gmail-guard.json`](../examples/hermes-gmail-guard.json))
and install it root-owned so the bot can't edit it:
```bash
sudo install -o root -g root -m 0644 hermes-gmail-guard.json /etc/hermes-gmail-guard.json
```
Add the Gmail section of [`examples/SOUL-gmail.md`](../examples/SOUL-gmail.md) to the bot's
SOUL.md, then restart the gateway.

## Adding an inbox
1. `sudo -u gmail-mcp -H /home/gmail-mcp/bin/gm auth add --label alice` (always read-only).
2. The person opens the printed link on any device and approves. The browser then fails to load
   `http://127.0.0.1:<port>/…`; that's expected. Copy that full URL.
3. On the server, within 5 minutes: `curl '<that URL>'`. **Use single quotes.** The URL contains
   `&`, and unquoted the shell splits it, giving "No authorization code was returned".
4. **Restart the bot's gateway.** The server loads accounts only at startup.
5. Add the label to `inboxes` (and the person's Discord ID to `people`) in the guard config and
   reinstall it.

Anyone can revoke access at <https://myaccount.google.com/permissions>, or run
`gm auth remove <email>`. Tokens also stop working when that person changes their Google password.

## Scheduled jobs
Cron runs have nobody to click an approval, so Hermes blocks them (`approvals.cron_mode: deny`). To
let one job read one inbox, add it to `cron` in `/etc/hermes-gmail-guard.json`:
```json
"cron": {"<job id from `hermes cron list`>": ["alice"]}
```
The `cron` section is honored only from the root-owned `/etc` file. No restart is needed. Only the
job that calls Gmail needs listing, not scripts that post its output. Changing a job's schedule
keeps its ID; a recreated job needs a new entry. To test, run `hermes cron run <id>` and check the
agent log for `tool mcp__gmail__…`.

## Pitfalls
- **Tool names are `mcp__gmail__<tool>`** (double underscores) in current Hermes, and some docs
  still show `mcp_gmail_<tool>`. Check `agent.log`. A plugin that matches the wrong prefix guards
  nothing and gives no error.
- **Add an inbox, restart the bot.** Otherwise it reports no inboxes connected.
- **Redaction is deliberately aggressive.** Sign-up links whose URLs look like login or confirm
  links get hidden; open those emails in Gmail.
- **Dependencies:** install with `npm ci --ignore-scripts`. Be wary of packages published in the
  last few days (`npm audit fix --before=<date>`); supply-chain attacks often get caught within a
  week.
