#!/usr/bin/env bash
set -euo pipefail

: "${SSHD_PORT:=2222}"
: "${SSH_AUTH_SOCKET:=/tmp/ssh-agent.sock}"
: "${CONFIG_ROOT:=/root/.config/simple_sync}"

mkdir -p /root/.ssh /var/run/sshd /srv/local /srv/remote "$CONFIG_ROOT/profiles"

# Generate host keys if missing
ssh-keygen -A >/dev/null 2>&1

# Generate a demo keypair for root and authorize it for sshd.
if [ ! -f /root/.ssh/id_ed25519 ]; then
    ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" -q
fi
cat /root/.ssh/id_ed25519.pub > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Start an ssh-agent with a deterministic socket path so pre_connect_command can target it.
eval "$(ssh-agent -a "$SSH_AUTH_SOCKET" -s)" >/tmp/agent.env
ssh-add /root/.ssh/id_ed25519
echo "ssh-agent running on $SSH_AUTH_SOCKET"

# Seed a demo profile that exercises pre_connect_command and SSH agent usage.
cat > "$CONFIG_ROOT/profiles/demo.toml" <<EOF
[profile]
name = "demo"
description = "Local vs SSH demo using ssh-agent"
topology = "pair"

[conflict]
policy = "newest"

[ignore]
patterns = []

[schedule]
enabled = false
interval_seconds = 3600
run_on_start = true

[ssh]
use_agent = true
pre_connect_command = "ssh-add -l"
ssh_command = "ssh -p ${SSHD_PORT} -o StrictHostKeyChecking=no"

[ssh.env]
SSH_AUTH_SOCK = "${SSH_AUTH_SOCKET}"

[endpoints.local]
type = "local"
path = "/srv/local"

[endpoints.remote]
type = "ssh"
host = "localhost"
path = "/srv/remote"
EOF

echo "Demo profile written to $CONFIG_ROOT/profiles/demo.toml"
echo "Local endpoint: /srv/local"
echo "Remote endpoint: /srv/remote (via ssh on port ${SSHD_PORT})"
echo "SSH agent: ${SSH_AUTH_SOCKET}"
echo "To test: simple-sync --config-dir ${CONFIG_ROOT%/profiles} run demo --dry-run"

exec /usr/sbin/sshd -D -e -p "$SSHD_PORT"
