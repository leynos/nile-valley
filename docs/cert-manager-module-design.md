# Cert-manager module design

## Purpose

Provide an OpenTofu module that deploys cert-manager and exposes ClusterIssuer
resources for ACME (Automated Certificate Management Environment, Let's
Encrypt) and Vault. The module supports both render mode (Flux-ready manifests)
and apply mode (direct Kubernetes provisioning) so the `nile-valley-infra-k8s`
action can converge shared Transport Layer Security (TLS) fixtures on each run.

## Goals

- Deploy cert-manager via Helm using the Jetstack Open Container Initiative
  (OCI) chart repository.
- Create ACME staging and production ClusterIssuers with DNS-01 webhook
  configuration for Namecheap.
- Optionally create a Vault ClusterIssuer using token-based authentication and
  a supplied CA bundle.
- Emit issuer names, secret references, and CA bundle material for downstream
  modules.
- Render Flux manifests under `platform/sources/` and `platform/cert-manager/`
  with a Kustomization entrypoint.
- Provide policy and test coverage for manifest and plan validation.

## Non-goals

- Managing the Namecheap webhook source code or container image pipeline.
- Supporting Vault AppRole authentication in this module (token only).
- Configuring cert-manager `Certificate` resources; workload teams own those.

## Decisions

- **Chart source**: Use the Jetstack OCI registry
  (`oci://quay.io/jetstack/charts`) to align with the declarative TLS guide.
- **Chart version**: Pin `v1.19.2` to match the TLS guide and avoid untracked
  updates.
- **High availability**: Default controller, webhook, and cainjector replicas
  to three. Render PodDisruptionBudgets when webhook or cainjector replicas are
  greater than one.
- **ACME issuers**: Always include staging and production ClusterIssuers (both
  can be toggled off), using the Namecheap DNS-01 webhook with required
  `groupName` and `solverName`.
- **Namecheap secret format**: Expect a single Secret containing `api-key` and
  `api-user` keys to align with the TLS guide.
- **Vault issuer**: Keep the Vault issuer optional (default off), use
  token-based authentication, and require a PEM-encoded CA bundle input when
  enabled. Provide optional rendering of a Secret containing the CA bundle for
  downstream consumption.
- **GitOps layout**: Render manifests into
  `platform/sources/cert-manager-repo.yaml`,
  `platform/sources/namecheap-webhook-repo.yaml` (optional), and
  `platform/cert-manager/` (namespace, helm releases, issuers, PDBs, CA bundle,
  kustomization).

## Interfaces

### Inputs

Key inputs include:

- `acme_email` and ACME issuer names/servers.
- `namecheap_api_secret_name` plus optional key overrides.
- `vault_server`, `vault_pki_path` (Vault Public Key Infrastructure signing
  path), `vault_token_secret_name`, and `vault_ca_bundle_pem`.
- `webhook_release_*` settings for the optional Namecheap webhook Helm release.
- `ca_bundle_secret_*` settings for optional CA bundle Secret rendering.

### Outputs

The module exposes:

- Issuer names and `ClusterIssuer` references for ACME and Vault.
- Secret references for ACME account keys, Namecheap API credentials, and Vault
  token.
- Vault CA bundle material (raw and base64) and optional Secret reference.
- Rendered manifests map for GitOps pipelines.

## Validation and policy

- **Static checks**: `tofu fmt -check`, `tofu validate`, and `tflint`.
- **Policy checks**: Conftest policies validate rendered manifests and plan
  output for HelmRelease pinning, issuer configuration, and webhook alignment.
- **Tests**: Terratest verifies render output, validation errors, plan policy,
  and optional apply-mode behaviour.

## Risks and mitigations

- **Webhook supply chain**: The module assumes a privately maintained webhook
  chart and does not source public images directly.
- **Namecheap API IP whitelisting**: Operators must manage static egress or
  IP whitelisting; the module keeps the webhook optional to accommodate
  alternative DNS providers.
- **Vault TLS trust**: Require explicit CA bundle input and expose it for
  downstream validation.
