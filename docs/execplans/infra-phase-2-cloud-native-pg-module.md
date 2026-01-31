# CloudNativePG OpenTofu module plan for core cluster services

This Execution Plan (ExecPlan) is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

No `PLANS.md` file exists in this repository, so there is no additional plan
policy to follow.

## Purpose / Big Picture

Deliver the Phase 2.3 CloudNativePG (CNPG) module so the `nile-valley-infra-k8s`
action can render Flux-ready manifests into `nile-valley-infra` and converge a
high-availability PostgreSQL cluster on every run. Success is visible when the
new OpenTofu module can render a `platform/databases` tree containing the CNPG
operator HelmRelease, PostgreSQL Cluster resources with PostGIS support, S3
backup configuration, and when its outputs expose connection endpoints and sync
policy contracts for downstream applications.

The module deploys both the CloudNativePG operator (via Flux HelmRelease) and
the CNPG Cluster CustomResourceDefinition (CRD) for PostgreSQL. It integrates
with the `vault_eso` module for credential management via External Secrets
Operator.

## Progress

- [x] (Done) Draft the initial ExecPlan for the CloudNativePG module.
- [x] (Done) Scaffold module structure following vault_eso patterns.
- [x] (Done) Implement module files (main.tf, locals.tf, manifests.tf,
  resources.tf, outputs.tf, versions.tf, variables-*.tf).
- [x] (Done) Create examples (render and basic).
- [x] (Done) Implement OPA/Conftest policies for rendered manifests.
- [x] (Done) Add Terratest coverage with validation and policy tests.
- [x] (Done) Create render-policy script and Makefile targets.
- [ ] (Pending) Initialize Go module dependencies and run tests.
- [ ] (Pending) Run repo-wide gates (`make check-fmt`, `make lint`, and `make test`).
- [ ] (Pending) Update roadmap entry to mark CloudNativePG as done.

## Surprises & Discoveries

(To be updated as work proceeds.)

## Decision Log

- Decision: Deploy both CNPG operator AND Cluster resource in single module.
  Rationale: Simplifies consumption for nile-valley-infra-k8s action; operator and
  cluster are tightly coupled and always deployed together. Date/Author:
  2025-12-25 / Claude.

- Decision: Use S3-compatible storage (DigitalOcean Spaces) for backups.
  Rationale: Aligns with existing DigitalOcean infrastructure; Barman object
  store supports S3-compatible endpoints natively. Date/Author: 2025-12-25 /
  Claude.

- Decision: Integrate with ESO via existing vault_eso ClusterSecretStore.
  Rationale: Centralizes secret management; PostgreSQL credentials can be
  managed in Vault and synchronized via ExternalSecret resources. Date/Author:
  2025-12-25 / Claude.

- Decision: Use PostGIS 16-3.4 image for spatial data support.
  Rationale: Enables geospatial queries for the Nile Valley platform; PostGIS is
  the standard PostgreSQL extension for spatial data. Date/Author: 2025-12-25 /
  Claude.

- Decision: Default to 3-instance HA cluster with PodDisruptionBudget.
  Rationale: Provides high availability with automatic failover; PDB ensures
  controlled disruption during updates. Date/Author: 2025-12-25 / Claude.

## Outcomes & Retrospective

(To be completed when work is finished.)

## Context and Orientation

The CloudNativePG module lives alongside the existing OpenTofu modules in
`infra/modules`. The `vault_eso`, `cert_manager`, and `traefik` modules
demonstrate the expected render/apply pattern, policy structure, and Terratest
conventions. Key paths and references:

- `infra/modules/vault_eso/` for the most recent module structure including
  split variable files, `rendered_manifests` outputs, and OPA/Conftest policies.
- `docs/cloud-native-ephemeral-previews.md` (lines 904-960) for the Cluster
  spec and architecture decisions.
- `infra/testutil/` for shared Terratest helpers (`TerraformEnvVars`,
  `SetupTerraform`).
- `scripts/vault-eso-render-policy.sh` for render-policy automation patterns.
- `docs/opentofu-coding-standards.md` and
  `docs/opentofu-module-unit-testing-guide.md` for HCL rules and testing
  approach.
- `docs/ephemeral-previews-roadmap.md` for the roadmap entry that must be
  marked done when this module is complete.

Definitions used in this plan:

- **CNPG**: CloudNativePG — a Kubernetes operator for managing PostgreSQL
  clusters with high availability, backups, and failover.
- **Cluster**: The CNPG custom resource that defines a PostgreSQL cluster.
- **PostGIS**: A PostgreSQL extension for geographic object storage and
  spatial queries.
- **Barman**: The backup and recovery manager used by CNPG for S3-compatible
  object store backups.
- **ScheduledBackup**: A CNPG custom resource for defining backup schedules.
- **PodDisruptionBudget (PDB)**: Kubernetes resource limiting voluntary
  disruptions to ensure availability.
- **ESO**: External Secrets Operator — synchronizes secrets from Vault into
  Kubernetes.
- **ExternalSecret**: An ESO resource that defines which secrets to fetch.
- **Render mode**: OpenTofu emits manifests for Flux to apply via GitOps.
- **Apply mode**: OpenTofu applies resources directly to a live cluster.
- **Synchronization policy contract**: A set of outputs that downstream modules
  can consume to reference connection endpoints and credentials.

## Plan of Work

### Phase 1: Module Scaffolding

Scaffold `infra/modules/cnpg` with the same structure as existing modules:

- `main.tf` — module entry and header comment
- `locals.tf` — derived values and endpoint construction
- `versions.tf` — provider requirements
- `variables-core.tf` — core module inputs (mode, namespaces, Helm settings)
- `variables-cluster.tf` — cluster configuration (instances, storage, PostGIS)
- `variables-backup.tf` — S3 backup configuration
- `variables-credentials.tf` — ESO integration settings
- `manifests.tf` — rendered manifest construction
- `resources.tf` — apply-mode Kubernetes resources
- `outputs.tf` — module outputs including sync policy contract
- `.tflint.hcl` — linting configuration
- `examples/basic/` — apply-mode example
- `examples/render/` — render-mode example
- `policy/manifests/` — OPA policies for rendered manifests
- `tests/` — Terratest suites

### Phase 2: Operator Manifests

Implement manifests for the CNPG operator:

1. **HelmRepository** — source for cloudnative-pg charts in flux-system.
2. **Operator Namespace** — `cnpg-system` namespace manifest.
3. **Operator HelmRelease** — CNPG operator deployment with pinned version.

### Phase 3: Cluster Configuration

Implement the CNPG Cluster resource:

1. **Cluster Namespace** — `databases` namespace manifest.
2. **Cluster Resource** — CNPG Cluster CRD with:
   - 3-instance HA configuration
   - PostGIS bootstrap with initdb
   - Storage class and size settings
   - Resource limits
3. **PodDisruptionBudget** — when instances > 1, ensure minAvailable.

### Phase 4: Backup Integration

Implement S3-compatible backup configuration:

1. **S3 Credentials Secret** — stores access key and secret key for Spaces.
2. **Barman Object Store** — integrated into Cluster spec with:
   - S3 destination path
   - Endpoint URL for DigitalOcean Spaces
   - WAL archiving configuration
   - Retention policy
3. **ScheduledBackup** — cron-based backup scheduling.

### Phase 5: ESO Integration

Implement External Secrets Operator integration:

1. **ExternalSecret (Superuser)** — fetches superuser credentials from Vault.
2. **ExternalSecret (Application)** — fetches app credentials from Vault.
3. **ExternalSecret (Backup)** — fetches S3 credentials from Vault (optional).

### Phase 6: Outputs

Expose outputs for downstream consumption:

- `primary_endpoint` — read-write endpoint for PostgreSQL.
- `replica_endpoint` — read-only endpoint for read replicas.
- `sync_policy_contract` — structured object with endpoints, database info,
  credential references, and backup status.
- `rendered_manifests` — map for render mode.

### Phase 7: Open Policy Agent (OPA) Policies

Create OPA/Conftest policies for rendered manifests:

- **helmrelease.rego** — pinned chart versions, correct sourceRef.
- **cluster.rego** — instances > 0, storage class and size, bootstrap config,
  backup configuration, PDB presence for HA.

### Phase 8: Terratest Coverage

Implement Terratest coverage:

- **Render tests** — validate output structure and manifest content.
- **Validation tests** — table-driven cases for invalid inputs.
- **Policy tests** — both acceptance and rejection scenarios.

### Phase 9: Integration

- Create `scripts/cnpg-render-policy.sh` script.
- Add `cnpg-test` and `cnpg-policy` Makefile targets.
- Update `INFRA_TEST_TARGETS` to include new targets.

## Concrete Steps

All commands should be run from the repository root directory.

1. Module scaffolding completed:

   ```text
   infra/modules/cnpg/
   ├── .tflint.hcl
   ├── main.tf
   ├── locals.tf
   ├── manifests.tf
   ├── resources.tf
   ├── outputs.tf
   ├── versions.tf
   ├── variables-core.tf
   ├── variables-cluster.tf
   ├── variables-backup.tf
   ├── variables-credentials.tf
   ├── examples/
   │   ├── basic/
   │   └── render/
   ├── policy/
   │   └── manifests/
   └── tests/
   ```

2. Generate provider lock files:

   ```bash
   tofu -chdir=infra/modules/cnpg init -input=false -no-color
   tofu -chdir=infra/modules/cnpg/examples/render init -input=false -no-color
   ```

3. Initialize Go module for tests:

   ```bash
   cd infra/modules/cnpg/tests && go mod tidy
   ```

4. Run module-specific tests:

   ```bash
   make cnpg-test
   make cnpg-policy
   ```

5. Run repository-wide gates:

   ```bash
   make check-fmt
   make lint
   make test
   ```

## Validation and Acceptance

The work is complete when all of the following are true:

- `infra/modules/cnpg` exists with module files, examples, policies, and
  Terratest suites matching repository conventions.
- Render mode produces a non-empty `rendered_manifests` map containing:
  - `platform/sources/cloudnative-pg-repo.yaml`
  - `platform/databases/namespace-cnpg-system.yaml`
  - `platform/databases/namespace-databases.yaml`
  - `platform/databases/cnpg-operator-helmrelease.yaml`
  - `platform/databases/nile-valley-pg-cluster.yaml`
  - `platform/databases/pdb-cnpg-cluster.yaml` (when instances > 1)
  - `platform/databases/s3-credentials-secret.yaml` (when backup enabled)
  - `platform/databases/scheduled-backup.yaml` (when backup enabled)
  - `platform/databases/external-secret-superuser.yaml` (when ESO enabled)
  - `platform/databases/external-secret-app.yaml` (when ESO enabled)
  - `platform/databases/kustomization.yaml`
- Outputs include sync policy contract with endpoints, database info, and
  credential references.
- `make cnpg-test` and `make cnpg-policy` pass locally.
- The CloudNativePG module entry in `docs/ephemeral-previews-roadmap.md` is
  marked done.

## Rendered Manifests Structure

```text
platform/
├── sources/
│   └── cloudnative-pg-repo.yaml        # HelmRepository
└── databases/
    ├── namespace-cnpg-system.yaml      # Operator namespace
    ├── namespace-databases.yaml        # Cluster namespace
    ├── cnpg-operator-helmrelease.yaml  # Operator HelmRelease
    ├── nile-valley-pg-cluster.yaml        # CNPG Cluster resource
    ├── pdb-cnpg-cluster.yaml           # PodDisruptionBudget
    ├── s3-credentials-secret.yaml      # S3 backup credentials
    ├── scheduled-backup.yaml           # Backup schedule
    ├── external-secret-superuser.yaml  # ESO for superuser
    ├── external-secret-app.yaml        # ESO for app credentials
    └── kustomization.yaml              # Kustomization manifest
```

## Sync Policy Contract Output Structure

```hcl
output "sync_policy_contract" {
  description = "Contract for downstream workloads to consume PostgreSQL"
  value = {
    cluster = {
      name      = local.cluster_name
      namespace = local.cluster_namespace
    }
    endpoints = {
      primary = {
        host = local.primary_endpoint
        port = 5432
      }
      replica = {
        host = local.replica_endpoint
        port = 5432
      }
    }
    database = {
      name  = local.database_name
      owner = local.database_owner
    }
    credentials = {
      superuser_secret = {
        name      = "${local.cluster_name}-superuser"
        namespace = local.cluster_namespace
      }
      app_secret = {
        name      = "${local.cluster_name}-app"
        namespace = local.cluster_namespace
      }
    }
    backup = var.backup_enabled ? {
      destination_path = var.backup_destination_path
      schedule         = var.backup_schedule
    } : null
    postgis_enabled = var.postgis_enabled
  }
}
```

## Interfaces and Dependencies

The module declares the following providers in `versions.tf`:

- `opentofu/kubernetes` ~> 2.25.0
- `opentofu/helm` ~> 2.13.0

**Required inputs:**

- `mode` — `render` or `apply`.

**Key optional inputs:**

- `operator_namespace` — namespace for CNPG operator (default: `cnpg-system`).
- `cluster_namespace` — namespace for PostgreSQL cluster (default: `databases`).
- `cluster_name` — name of the CNPG Cluster (default: `nile-valley-pg`).
- `instances` — number of PostgreSQL instances (default: `3`).
- `storage_size` — persistent volume size (default: `10Gi`).
- `storage_class` — storage class name (default: `do-block-storage`).
- `postgis_enabled` — enable PostGIS extension (default: `true`).
- `backup_enabled` — enable S3 backups (default: `false`).
- `backup_destination_path` — S3 bucket path for backups.
- `backup_endpoint_url` — S3-compatible endpoint URL.
- `eso_enabled` — enable ESO integration (default: `false`).
- `eso_cluster_secret_store_name` — ClusterSecretStore name from vault_eso.

**Expected outputs:**

- `primary_endpoint` — read-write service endpoint.
- `replica_endpoint` — read-only service endpoint.
- `sync_policy_contract` — structured contract for downstream consumers.
- `rendered_manifests` — map for render mode.

## Integration with Existing Infrastructure

The module integrates with:

1. **vault_eso module** — provides ClusterSecretStore for credential management.
2. **cert_manager module** — optional Transport Layer Security (TLS) for
   PostgreSQL connections.
3. **nile-valley-infra-k8s action** — consumes `rendered_manifests` and
   commits to GitOps repository.

## Revision Note

- 2025-12-25: Initial implementation of the CloudNativePG module. Created
  module structure, manifests, policies, tests, and Makefile targets.
