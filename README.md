# nile-valley

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](
https://deepwiki.com/leynos/nile-valley)

Nile Valley is the shared infrastructure for ephemeral preview environments. It
provisions Kubernetes clusters, renders platform fixtures, and commits GitOps
manifests so FluxCD can reconcile multiple applications that supply a Helm
chart.

## Repository layout

- `.github/actions/nile-valley-infra-k8s`: composite action for cluster
  provisioning and GitOps rendering.
- `infra/`: OpenTofu modules, policies, and cluster roots.
- `scripts/`: Python automation for input resolution, provisioning, rendering,
  and GitOps commits.
- `deploy/charts/example-app`: example Helm chart showing the contract Nile
  Valley expects from application charts.

## Development setup

Install Bun and Python tooling, then pull dependencies through the Makefile:

```bash
make deps
```

The test suite relies on `uv` for isolated Python runs. Ensure `uv` is
available in the PATH before running `make test`.

## OpenTofu provider lockfile

OpenTofu pins provider versions in `.terraform.lock.hcl`. Commit this file so
local and CI environments resolve identical provider builds. When upgrading
providers with `tofu init -upgrade`, include the updated lockfile in the
commit.

## Formatting, linting, and tests

Use the Makefile targets for formatting, linting, and tests:

```bash
# Format scripts (Biome)
make fmt

# Lint scripts, actions, and infra
make lint

# Check formatting only (no writes)
make check-fmt

# Run Python unit tests for automation scripts
make test
```

Documentation linting and diagram validation:

```bash
make markdownlint
make nixie
```

## Example Helm chart

The example chart in `deploy/charts/example-app` demonstrates the values Nile
Valley expects application charts to support.

| Value                     | Default                     | Purpose                                                          |
| ------------------------- | --------------------------- | ---------------------------------------------------------------- |
| `existingSecretName`      | `""`                        | Name of a Secret to source environment variables from.           |
| `secretEnvFromKeys`       | `{}`                        | Map environment variables to keys in `existingSecretName`.       |
| `allowMissingSecret`      | `true`                      | Permit rendering when the Secret is absent.                      |
| `sessionSecret.enabled`   | `false`                     | Enable mounting a session signing key from a Secret.             |
| `sessionSecret.name`      | `"example-app-session-key"` | Secret name for the session signing key.                         |
| `sessionSecret.keyName`   | `"session_key"`             | Secret key containing the signing key bytes.                     |
| `sessionSecret.mountPath` | `"/var/run/secrets"`        | Mount path for the session key file.                             |

## Documentation

Start with the platform overview in `docs/cloud-native-ephemeral-previews.md`
and the roadmap in `docs/ephemeral-previews-roadmap.md`.
