#!/usr/bin/env bash
# vault-setup.sh — First-time Ansible Vault setup for new team members
# Run this once after cloning the repo.

set -euo pipefail

echo "╔══════════════════════════════════════╗"
echo "║   Ansible Vault Setup                ║"
echo "╚══════════════════════════════════════╝"
echo ""

if [ -f ".vault-password" ]; then
  echo "WARNING: .vault-password already exists. Skipping creation."
  echo "If you need to reset it, delete .vault-password and re-run this script."
  exit 0
fi

echo "Enter the vault password (get this from your team lead):"
read -r -s VAULT_PASSWORD

if [ ${#VAULT_PASSWORD} -lt 8 ]; then
  echo "ERROR: Password must be at least 8 characters."
  exit 1
fi

echo "${VAULT_PASSWORD}" > .vault-password
chmod 600 .vault-password
echo ""
echo "Created .vault-password (chmod 600)"

echo ""
echo "Verifying vault access..."
if ansible-vault view ansible/vault/secrets.yml \
  --vault-password-file .vault-password > /dev/null 2>&1; then
  echo "Vault access verified."
else
  echo "NOTE: secrets.yml is not yet encrypted."
  echo "To encrypt: ansible-vault encrypt ansible/vault/secrets.yml"
fi

echo ""
echo "Setup complete. Never commit .vault-password to git."
