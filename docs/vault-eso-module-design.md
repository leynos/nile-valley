# Vault + External Secrets Operator module design

This document records the design decisions for the `vault_eso` OpenTofu module
that integrates Kubernetes workloads with the external Vault appliance via
External Secrets Operator (ESO).

## Overview

The module deploys External Secrets Operator and configures ClusterSecretStore
resources that connect to the existing Vault appliance provisioned by the
`vault_appliance` OpenTofu module and initialized by the
`bootstrap-vault-appliance` GitHub Action.

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DigitalOcean Infrastructure                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    Vault Appliance (vault_appliance module)           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐   │  │
│  │  │  Droplet 1  │  │  Droplet 2  │  │      Load Balancer          │   │  │
│  │  │   (Vault)   │  │   (Vault)   │  │  (HTTPS termination)        │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ HTTPS (AppRole auth)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Kubernetes Cluster (DOKS)                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    vault_eso module resources                         │  │
│  │  ┌─────────────────────┐  ┌─────────────────────────────────────────┐ │  │
│  │  │  External Secrets   │  │         ClusterSecretStore             │ │  │
│  │  │     Operator        │◀─│  ┌─────────────────────────────────┐   │ │  │
│  │  │   (HelmRelease)     │  │  │           KV v2                 │   │ │  │
│  │  └─────────────────────┘  │  └─────────────────────────────────┘   │ │  │
│  │                           └─────────────────────────────────────────┘ │  │
│  │  ┌─────────────────────┐  ┌─────────────────────────────────────────┐ │  │
│  │  │  AppRole Auth       │  │       Workload Namespace                │ │  │
│  │  │     Secret          │  │  ┌─────────────────────────────────┐   │ │  │
│  │  │ (role_id/secret_id) │  │  │      ExternalSecret             │   │ │  │
│  │  └─────────────────────┘  │  │  (created by application team)  │   │ │  │
│  │                           │  └─────────────────────────────────┘   │ │  │
│  │                           └─────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

DOKS = DigitalOcean Kubernetes Service

## Design Decisions

### D1: Authentication Method — Application Role (AppRole)

**Decision:** Use AppRole authentication for ESO to connect to the external
Vault appliance.

**Rationale:** The `bootstrap-vault-appliance` action already provisions an
AppRole with the `doks-deployer` identity, including a `role_id` and
`secret_id`. ESO can consume these credentials to authenticate without
requiring Kubernetes service account token reviewer access on the external
Vault, which would require additional configuration and network access.

**Trade-offs:**

- AppRole credentials must be rotated periodically (handled by the bootstrap
  action with `rotate_secret_id` option).
- Credentials are stored as Kubernetes Secrets rather than dynamically obtained.
- Simpler setup than Kubernetes auth method, which requires Vault to call back
  to the Kubernetes API server.

### D2: External Secrets Operator Chart Version

**Decision:** Pin ESO chart version to `1.1.1` from the
`oci://ghcr.io/external-secrets/charts` repository.

**Rationale:** Uses the official OCI registry from the External Secrets project
to ensure supply chain integrity. Version 1.1.1 is the latest stable release as
of December 2025 with full support for Vault provider and ClusterSecretStore
resources.

### D3: ClusterSecretStore vs SecretStore

**Decision:** Provide ClusterSecretStore resources (cluster-scoped) rather than
namespace-scoped SecretStore resources.

**Rationale:**

- ClusterSecretStore allows any namespace to reference the same Vault
  connection without duplicating configuration.
- Reduces the operational burden of managing per-namespace SecretStore
  resources.
- Aligns with the platform team managing shared infrastructure while
  application teams create ExternalSecret resources in their namespaces.

### D4: Supported Vault Secret Engines

**Decision:** Provide a ClusterSecretStore resource for Key-Value (KV) v2
secrets only.

**Rationale:** KV v2 covers the majority of secret storage use cases
(credentials, API keys, connection strings). Public Key Infrastructure (PKI)
certificate issuance is handled by cert-manager with Vault PKI issuer, which is
the appropriate tool for dynamic certificate generation. ESO's standard Vault
provider only supports KV secret engines; PKI would require VaultDynamicSecret
generators, which add complexity without clear benefit given cert-manager's
capabilities.

### D5: Vault Agent Injector

**Decision:** Do not include Vault Agent Injector in the initial implementation.

**Rationale:**

- ESO provides a GitOps-native approach to secret synchronization that aligns
  with the overall platform architecture.
- Vault Agent Injector adds complexity (sidecar injection, annotations, init
  containers) that is not required for the initial use cases.
- It can be added as a separate optional component in a future iteration if
  sidecar injection patterns are needed.

### D6: Sync Policy Contract Output

**Decision:** Expose a `sync_policy_contract` output that bundles secret store
references and mount paths for downstream workload consumption.

**Rationale:** Provides a stable interface for the `nile-valley-infra-k8s` action
and application modules to reference secret stores without depending on
internal naming conventions. The contract includes:

- Secret store name and kind for KV v2.
- Vault address for documentation purposes.
- Mount paths for constructing ExternalSecret `remoteRef.key` values.

### D7: Namespace Strategy

**Decision:** Deploy ESO to a dedicated `external-secrets` namespace (default)
with the AppRole authentication secret in the same namespace.

**Rationale:**

- Keeps ESO isolated from application workloads.
- The ClusterSecretStore references the auth secret in this namespace.
- Application teams create ExternalSecret resources in their own namespaces.

### D8: High Availability Configuration

**Decision:** Default to 2 replicas for ESO webhook with PodDisruptionBudget
(PDB).

**Rationale:**

- Ensures availability during node maintenance and rolling updates.
- The ESO webhook is critical for validating ExternalSecret resources.
- Aligns with the HA patterns established by the cert-manager module.

## Interface Summary

### Required Inputs

| Variable              | Type     | Description                                    |
| --------------------- | -------- | ---------------------------------------------- |
| `vault_address`       | `string` | HTTPS endpoint of the external Vault appliance |
| `vault_ca_bundle_pem` | `string` | PEM-encoded CA certificate for Vault TLS       |
| `approle_role_id`     | `string` | AppRole role_id for ESO authentication         |
| `approle_secret_id`   | `string` | AppRole secret_id (sensitive)                  |

### Key Optional Inputs

| Variable        | Type     | Default              | Description               |
| --------------- | -------- | -------------------- | ------------------------- |
| `mode`          | `string` | `"render"`           | `render` or `apply`       |
| `namespace`     | `string` | `"external-secrets"` | ESO namespace             |
| `kv_mount_path` | `string` | `"secret"`           | KV v2 mount path in Vault |
| `chart_version` | `string` | `"1.1.1"`            | ESO Helm chart version    |
| `replica_count` | `number` | `2`                  | ESO webhook replicas      |

### Outputs

| Output                         | Type          | Description                       |
| ------------------------------ | ------------- | --------------------------------- |
| `namespace`                    | `string`      | ESO namespace                     |
| `cluster_secret_store_kv_name` | `string`      | KV ClusterSecretStore name        |
| `cluster_secret_store_kv_ref`  | `object`      | KV store reference object         |
| `sync_policy_contract`         | `object`      | Contract for downstream consumers |
| `rendered_manifests`           | `map(string)` | GitOps manifests (render mode)    |

## Rendered Manifests (render mode)

The module produces the following GitOps-ready manifests:

- `platform/sources/external-secrets-repo.yaml` — HelmRepository
- `platform/vault/namespace.yaml` — Namespace
- `platform/vault/helmrelease.yaml` — ESO HelmRelease
- `platform/vault/approle-auth-secret.yaml` — AppRole credentials Secret
- `platform/vault/cluster-secret-store-kv.yaml` — KV v2 ClusterSecretStore
- `platform/vault/pdb-external-secrets-webhook.yaml` — PDB (when replicas > 1)
- `platform/vault/kustomization.yaml` — Kustomization manifest

## Integration Points

### bootstrap-vault-appliance Action

The action outputs used by this module:

- `approle-role-id` — mapped to `approle_role_id` input
- `approle-secret-id` — mapped to `approle_secret_id` input
- `vault-address` — mapped to `vault_address` input

### vault_appliance Module

The module outputs used for integration:

- `public_endpoint.ip` — Vault load balancer IP
- `ca_certificate` — PEM-encoded CA for TLS validation

### Application Workloads

Application teams create ExternalSecret resources referencing the
ClusterSecretStore:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: my-app-secrets
  namespace: my-app
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-kv  # From sync_policy_contract.kv_secret_store.name
    kind: ClusterSecretStore
  target:
    name: my-app-secrets
  data:
    - secretKey: database-password
      remoteRef:
        key: secret/data/my-app/database  # Using kv_mount_path
        property: password
```

## Security Considerations

1. **AppRole Secret Rotation:** The `approle_secret_id` should be rotated
   regularly using the `rotate_secret_id` option in the bootstrap action.

2. **CA Bundle Validation:** The module enforces that `vault_ca_bundle_pem` is
   provided to ensure TLS verification against the Vault endpoint.

3. **Secret Storage:** AppRole credentials are stored in a Kubernetes Secret
   that should be protected by role-based access control (RBAC) policies.

4. **Namespace Isolation:** ClusterSecretStore allows cross-namespace access
   but ExternalSecret resources must still be created by authorized workloads.

## Future Enhancements

- Vault Agent Injector support for sidecar injection patterns.
- Kubernetes auth method as an alternative to AppRole.
- PushSecret support for bidirectional secret synchronization.
- Webhook certificate management integration with cert-manager.
- VaultDynamicSecret generators for PKI certificate issuance (if cert-manager
  integration proves insufficient for specific use cases).

## Revision History

- 2025-12-20: Initial design document created.
