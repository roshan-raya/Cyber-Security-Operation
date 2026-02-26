#!/usr/bin/env bash
set -euo pipefail

PUBKEY_SRC="/ssh_pubkey/id_rsa.pub"
DEVOPS_HOME="/home/devops"
SSH_DIR="${DEVOPS_HOME}/.ssh"
AUTH_KEYS="${SSH_DIR}/authorized_keys"

echo "[patch-target] Starting. Waiting for SSH public key at ${PUBKEY_SRC} ..."

# Needed for sshd
mkdir -p /run/sshd

# Ensure .ssh exists with correct perms
mkdir -p "${SSH_DIR}"
chown -R devops:devops "${SSH_DIR}"
chmod 700 "${SSH_DIR}"

# Generate host keys if missing
ssh-keygen -A

# Wait up to 60s for key
for i in $(seq 1 60); do
  if [ -s "${PUBKEY_SRC}" ]; then
    break
  fi
  sleep 1
done

if [ ! -s "${PUBKEY_SRC}" ]; then
  echo "[patch-target] ERROR: SSH public key not found after 60s: ${PUBKEY_SRC}"
  exit 1
fi

# Install authorized key
cat "${PUBKEY_SRC}" > "${AUTH_KEYS}"
chown devops:devops "${AUTH_KEYS}"
chmod 600 "${AUTH_KEYS}"

echo "[patch-target] SSH key installed. Launching sshd..."
exec /usr/sbin/sshd -D -e
