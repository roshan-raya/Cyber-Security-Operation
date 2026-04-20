# Ansible Vault — Secrets Management

## Setup for new team members

1. Get the vault password from your team lead (never share over email/Slack)
2. Create the password file (never commit this):
   ```bash
   echo "YOUR_VAULT_PASSWORD" > .vault-password
   chmod 600 .vault-password
   ```
3. Verify you can decrypt:
   ```bash
   ansible-vault view ansible/vault/secrets.yml --vault-password-file .vault-password
   ```

## Encrypting the secrets file

```bash
ansible-vault encrypt ansible/vault/secrets.yml --vault-password-file .vault-password
```

## Editing after encryption

```bash
ansible-vault edit ansible/vault/secrets.yml --vault-password-file .vault-password
```

## Decrypting for inspection

```bash
ansible-vault view ansible/vault/secrets.yml --vault-password-file .vault-password
```

## What is stored here

| Variable | Purpose |
|---|---|
| vault_grafana_admin_password | Grafana admin login password |
| vault_grafana_admin_user | Grafana admin username |
| vault_ansible_ssh_key_comment | SSH key identifier label |

## Vault password rules

- Minimum 16 characters
- Never commit .vault-password to git (it is in .gitignore)
- Rotate every 90 days
- Store in your team password manager (1Password, Bitwarden, etc.)
