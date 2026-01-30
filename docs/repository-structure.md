# Repository design guide

This guide describes how the Nile Valley infrastructure repository is
organised and how the automation flows between directories. The intent is to
help new contributors find the right place to make changes.

## Top-level layout

- `.github/actions/`
  - `nile-valley-infra-k8s/`: Composite action that provisions a cluster and
    renders GitOps manifests.
  - `bootstrap-vault-appliance/`: Composite action that initialises the Vault
    appliance for secrets management.
- `infra/`
  - `clusters/`: OpenTofu roots for concrete clusters (e.g. `dev/`,
    `nile-valley-infra-k8s/`).
  - `modules/`: Reusable OpenTofu modules (DOKS, FluxCD, cert-manager, Vault,
    Valkey, CloudNativePG, etc.).
  - `backend-config/`: Shared OpenTofu backend configuration snippets.
- `scripts/`: Python helpers that power the composite actions (input
  resolution, provisioning, rendering, GitOps commits, output publishing).
- `deploy/charts/example-app/`: Example Helm chart illustrating the values
  contract expected by application charts.
- `docs/`: Architecture, module design, and operational guides.

## GitOps repositories (external)

Nile Valley interacts with two external Git repositories during normal
operation:

- `nile-valley-infra`: GitOps state for platform infrastructure (FluxCD
  sources, core services, and platform manifests).
- `nile-valley-apps`: GitOps state for application deployments and preview
  overlays.

Both repositories are provisioned and updated by automation. The composite
action in this repo commits platform manifests to `nile-valley-infra`, while
application repositories commit overlays to `nile-valley-apps`.

## Automation flow

1. The `nile-valley-infra-k8s` action resolves inputs via `scripts/` and
   provisions clusters using OpenTofu roots in `infra/clusters/`.
2. The action renders platform manifests with `infra/modules/platform_render`
   and commits the results into `nile-valley-infra`.
3. Application repositories build container images and commit HelmRelease
   overlays to `nile-valley-apps`, which FluxCD reconciles onto the cluster.

See `docs/cloud-native-ephemeral-previews.md` for the full architecture.

## Testing and policy

- Go tests live alongside infra modules under `infra/**/tests` and share a
  small helper module in `infra/testutil`.
- OpenTofu policy checks (Conftest) are stored in `infra/modules/*/policy` and
  cluster policy checks live under `infra/clusters/*/policy`.
- Python automation is unit-tested under `scripts/tests`.

## Example chart

The example Helm chart in `deploy/charts/example-app` documents the values Nile
Valley expects application charts to implement. Use it as a reference when
adapting another application to the platform.
