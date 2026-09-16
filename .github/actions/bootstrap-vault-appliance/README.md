# bootstrap-vault-appliance action

Initializes or verifies the DigitalOcean Vault appliance using the
`scripts/bootstrap_vault_appliance.py` helper. The action installs `uv`, the
Vault command-line interface (CLI), and `doctl`, seeds the helper's state file
from supplied secrets when provided, and outputs the AppRole credentials for
downstream workflows. Re-running the action is idempotent: the helper inspects
the existing appliance and only rotates the AppRole secret identifier when
requested.

## Inputs

- `environment` (required): Logical environment identifier used to derive the
  default droplet tag.
- `vault_address` (required): HTTPS endpoint served by the Vault load balancer.
- `digitalocean_token` (required, secret): Token with access to the Vault
  droplet tag.
- `droplet_tag` (optional): Overrides the default `vault-<environment>` tag.
- `ca_certificate` (optional): PEM (Privacy-Enhanced Mail) or base64-encoded CA
  (certificate authority) bundle passed to `VAULT_CACERT`.
- `bootstrap_state` (optional): JSON or base64 JSON payload for the helper's
  state file (unseal keys, root token, AppRole credentials).
- `state_path` (optional): Destination for the state file. Defaults to
  `$RUNNER_TEMP/vault-bootstrap/<environment>/state.json`.
- `ssh_private_key` / `ssh_user` (optional): Credentials for the droplet health
  probe executed before bootstrap.
- AppRole (Application Role) and KV (key-value) settings: `kv_mount_path`,
  `approle_name`, `approle_policy_name`, `approle_policy`, `token_ttl`,
  `token_max_ttl`, `secret_id_ttl`, `rotate_secret_id`.
- `key_shares` / `key_threshold` (optional): Vault initialization parameters.
- `vault_cli_version` (optional): Vault CLI version to install. Defaults to
  `1.17.6`.

## Outputs

- `vault-address`: Vault endpoint used for the run (mirrors the input).
- `ca-certificate-path`: Path to the CA bundle written for the run.
- `state-file`: Path to the helper's persisted state file on the runner.
- `approle-role-id`: Resolved AppRole role identifier.
- `approle-secret-id`: Secret identifier created or reused for the AppRole.

## Example usage

```yaml
jobs:
  bootstrap-vault:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Bootstrap Vault appliance
        id: vault
        uses: ./.github/actions/bootstrap-vault-appliance
        with:
          environment: dev
          vault_address: https://vault.dev.example.test
          digitalocean_token: ${{ secrets.DIGITALOCEAN_TOKEN }}
          ca_certificate: ${{ secrets.VAULT_CA_PEM }}
          bootstrap_state: ${{ secrets.VAULT_BOOTSTRAP_STATE }}
      - name: Export AppRole credentials
        run: |
          cat >> "$GITHUB_ENV" <<EOF
          VAULT_ROLE_ID=${{ steps.vault.outputs.approle-role-id }}
          VAULT_SECRET_ID=${{ steps.vault.outputs.approle-secret-id }}
          EOF
```
