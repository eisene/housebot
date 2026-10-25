#!/usr/bin/env bash
# gmail-mcp-setup.sh — isolated, read-only Gmail MCP server for the family bot.
#
# Run as:  sudo ./setup.sh        (safe to re-run; rebuilds the app)
#
# Before running, put two files in $STAGE (default: ~/gmail-mcp-staging of the sudo user):
#   oauth-client.json   Google Cloud "Desktop app" OAuth client (gmail.readonly scope only)
#   bot.pub             public key the bot user will SSH in with (ed25519)
# and download + verify a Node tarball to $NODE_TAR, setting NODE_SHA to its sha256.
# Every setting below can be overridden from the environment, e.g.
#   sudo NODE_TAR=/path/node.tar.xz NODE_SHA=... TZ_NAME=Europe/Berlin ./setup.sh
#
# What it does:
#   1. Creates system user `gmail-mcp` (home 0700, no password, key-only SSH).
#   2. Installs Node v26.12.1 (signature + checksum verified earlier) under its home.
#   3. Builds github.com/eisene/gmail-multi-mcp at a pinned commit with `npm ci
#      --ignore-scripts` from the lockfile, runs the test suite, drops dev deps.
#   4. Makes the code, Node, bin/ and ~/.ssh root-owned, so the server process
#      cannot modify its own code or who may log in.
#   5. Installs the OAuth client JSON (mode 600) into its data dir.
#   6. Authorizes the bot user's key with a forced command: that key can only
#      start the MCP server in locked (read-tools-only) mode. No shell, no pty,
#      no forwarding.
# It does NOT touch sshd config, Hermes config, or any existing user.
set -euo pipefail

INVOKER_HOME=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
U=${GMAIL_MCP_USER:-gmail-mcp}
H=/home/$U
REPO=${REPO:-https://github.com/eisene/gmail-multi-mcp.git}
COMMIT=${COMMIT:-8c99e321d6cfd23b7aae64fd292202de7a341400}
NODE_V=${NODE_V:-v26.12.1}
NODE_ARCH=${NODE_ARCH:-linux-arm64}
NODE_TAR=${NODE_TAR:-$INVOKER_HOME/node-dist/node-$NODE_V-$NODE_ARCH.tar.xz}
# sha256 of the official node-v26.12.1-linux-arm64.tar.xz; set your own for other versions/arches.
NODE_SHA=${NODE_SHA:-42aa04922591ee5d4dbc7740d452621acf28508239daa512f5ee8c47ee224fdb}
STAGE=${STAGE:-$INVOKER_HOME/gmail-mcp-staging}
PUBKEY_FILE=${PUBKEY_FILE:-$STAGE/bot.pub}
TZ_NAME=${TZ_NAME:-$(cat /etc/timezone 2>/dev/null || echo UTC)}

say() { printf '\n==> %s\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }

say "Checking inputs"
echo "$NODE_SHA  $NODE_TAR" | sha256sum -c -
test -s "$STAGE/oauth-client.json"   || { echo "missing $STAGE/oauth-client.json" >&2; exit 1; }
test -s "$PUBKEY_FILE"              || { echo "missing $PUBKEY_FILE" >&2; exit 1; }
PUBKEY=$(head -n1 "$PUBKEY_FILE")
[[ $PUBKEY == ssh-ed25519\ * ]]      || { echo "$PUBKEY_FILE is not an ed25519 key" >&2; exit 1; }

say "User $U"
if ! id "$U" >/dev/null 2>&1; then
  adduser --system --group --home "$H" --shell /bin/bash --disabled-password \
          --comment "Gmail MCP server (read-only, for the household bot)" "$U"
fi
passwd -l "$U" >/dev/null 2>&1 || true
chown "$U:$U" "$H"
chmod 0700 "$H"

say "Node $NODE_V"
rm -rf "$H/opt"
install -d -o root -g root -m 0755 "$H/opt"
tar -xJf "$NODE_TAR" -C "$H/opt"
ln -sfn "node-$NODE_V-$NODE_ARCH" "$H/opt/node"
chown -R root:root "$H/opt"
NODE="$H/opt/node/bin/node"
"$NODE" --version

say "Building gmail-multi-mcp @ ${COMMIT:0:12}"
rm -rf "$H/app"
install -d -o "$U" -g "$U" -m 0755 "$H/app"
sudo -u "$U" -H env -i HOME="$H" PATH="$H/opt/node/bin:/usr/bin:/bin" TZ="$TZ_NAME" \
  bash -euo pipefail -c '
    cd "$HOME/app"
    git init -q . && git remote add origin "'"$REPO"'"
    git fetch -q --depth 1 origin "'"$COMMIT"'"
    git checkout -q FETCH_HEAD
    test "$(git rev-parse HEAD)" = "'"$COMMIT"'"
    npm ci --ignore-scripts --no-audit --no-fund --loglevel=warn
    npm test 2>&1 | tail -n 8
    npm prune --omit=dev --ignore-scripts --no-audit --no-fund --loglevel=warn
    rm -rf "$HOME/.npm/_cacache"
  '
chown -R root:root "$H/app"
chmod -R go-w "$H/app"

say "Wrappers in $H/bin (root-owned)"
install -d -o root -g root -m 0755 "$H/bin"
cat > "$H/bin/serve" <<EOF
#!/bin/sh
# Forced command for the bot's SSH key. Ignores whatever command was asked for.
export GMAIL_MCP_HOME=$H/.gmail-multi-mcp
export GMAIL_MCP_LOCKED=1 GMAIL_MCP_FORCE_FILE_STORE=1 GMAIL_MCP_NO_BROWSER=1
export TZ=$TZ_NAME
cd "$H" && exec $NODE $H/app/dist/src/index.js
EOF
cat > "$H/bin/gm" <<'EOF'
#!/bin/sh
# Admin CLI, run by a human:  sudo -u gmail-mcp -H /home/gmail-mcp/bin/gm <args>
# e.g.  gm auth add --label alice     gm auth list     gm auth remove <email>     gm doctor
# Accounts can only ever be added read-only.
set -eu
case "${1:-} ${2:-}" in
  "auth add")
    for a in "$@"; do
      case "$a" in --tier|--tier=*) echo "gm: tier is fixed to readonly here" >&2; exit 2;; esac
    done
    shift 2; set -- auth add --tier readonly "$@";;
  "auth add-password"|"auth tier"|"auth allow")
    echo "gm: '$1 $2' is disabled on this host (OAuth readonly only)" >&2; exit 2;;
esac
export GMAIL_MCP_HOME=__H__/.gmail-multi-mcp GMAIL_MCP_FORCE_FILE_STORE=1 GMAIL_MCP_NO_BROWSER=1
cd "__H__" && exec __NODE__ __H__/app/dist/src/index.js "$@"
EOF
sed -i "s#__H__#$H#g; s#__NODE__#$NODE#g" "$H/bin/gm"
chown root:root "$H/bin/serve" "$H/bin/gm"
chmod 0755 "$H/bin/serve" "$H/bin/gm"

say "Data dir + OAuth client"
install -d -o "$U" -g "$U" -m 0700 "$H/.gmail-multi-mcp"
install -o "$U" -g "$U" -m 0600 "$STAGE/oauth-client.json" "$H/.gmail-multi-mcp/oauth-client.json"

say "SSH: bot key -> forced command only"
install -d -o root -g root -m 0755 "$H/.ssh"
printf 'restrict,command="%s/bin/serve" %s\n' "$H" "$PUBKEY" > "$H/.ssh/authorized_keys"
chown root:root "$H/.ssh/authorized_keys"
chmod 0644 "$H/.ssh/authorized_keys"

say "Checks"
sudo -u "$U" -H "$H/bin/gm" doctor 2>&1 | sed 's/^/   /' || true
sshd -T -C "user=$U,host=localhost,addr=127.0.0.1" 2>/dev/null \
  | grep -Ei '^(allowusers|denyusers|allowgroups|pubkeyauthentication|strictmodes) ' | sed 's/^/   sshd: /' || true
ls -ld "$H" "$H/app" "$H/bin" "$H/.ssh" "$H/.gmail-multi-mcp" | sed 's/^/   /'

cat <<EOF

Done. Next:
  1. Wire up the bot: register MCP server "gmail" (ssh -T $U@localhost with the bot key)
     and install the gmail-guard plugin. See docs/gmail.md.
  2. Connect each inbox (one person at a time, ~2 min each):
       sudo -u $U -H $H/bin/gm auth add --label <name>
     Open the printed link on any device, sign in, approve. The browser then fails to
     load http://127.0.0.1:<port>/... — copy that full URL and, on the server, run:
       curl '<that URL>'
     (Quote the URL in single quotes. Any local user can run the curl.)
  3. After adding or removing an inbox, restart the bot so the server reloads accounts:
       (as the bot user) hermes gateway restart
EOF
