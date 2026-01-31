# Vault and External Secrets Operator module plan for core cluster services

This Execution Plan (ExecPlan) is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

No `PLANS.md` file exists in this repository, so there is no additional plan
policy to follow.

## Purpose / Big Picture

Deliver the Phase 2.3 Vault + External Secrets Operator (ESO) module so the
`nile-valley-infra-k8s` action can render Flux-ready manifests into
`nile-valley-infra` and converge secrets synchronization on every run. Success is
visible when the new OpenTofu module can render a `platform/vault` tree
containing the ESO HelmRelease, ClusterSecretStore resources connected to the
existing Vault appliance, and when its outputs expose secret store names and
sync policy contracts for downstream workloads.

The module connects Kubernetes workloads to the external Vault appliance
provisioned by the `vault_appliance` OpenTofu module and initialized by the
`bootstrap-vault-appliance` GitHub Action. It does not deploy a new Vault
instance but rather bridges the existing Vault infrastructure with the
Kubernetes cluster via ESO.

## Progress

- [ ] (Pending) Draft the initial ExecPlan for the Vault + ESO module.
- [ ] (Pending) Confirm the module interface and record decisions in
  `docs/vault-eso-module-design.md`.
- [ ] (Pending) Implement module files, examples, policies, tests, render
  policy script, and README updates.
- [ ] (Pending) Update Makefile targets, lint coverage, and roadmap entry.
- [ ] (Pending) Generate provider lock files and run module-specific tests.
- [ ] (Pending) Run repo-wide gates (`make check-fmt`, `make lint`, and `make test`).

## Surprises & Discoveries

(To be updated as work proceeds.)

## Decision Log

(To be updated as work proceeds. Initial anticipated decisions below.)

- Decision: (Pending) Use AppRole authentication (a Vault authentication method
  for machine-to-machine access) for ESO to connect to the external Vault
  appliance. Rationale: The `bootstrap-vault-appliance` action already
  provisions an AppRole with `doks-deployer` identity; ESO can consume the
  role_id and secret_id to authenticate. Date/Author: Pending.

- Decision: (Pending) Pin External Secrets Operator chart version.
  Rationale: Ensures reproducible deployments and prevents unexpected breaking
  changes. Date/Author: Pending.

- Decision: (Pending) Provide ClusterSecretStore resources (cluster-scoped ESO
  resources for external secret provider connections) for both the KV v2
  (Vault's versioned key-value secrets engine) and optional PKI (public key
  infrastructure) engine. Rationale: Supports common secret consumption
  patterns (credentials and certificates) from the existing Vault
  infrastructure. Date/Author: Pending.

- Decision: (Pending) Optionally deploy Vault Agent Injector for sidecar
  injection patterns. Rationale: Provides an alternative secret delivery
  mechanism for workloads that require file-based secrets or dynamic credential
  rotation. Date/Author: Pending.

## Outcomes & Retrospective

(To be completed when work is finished.)

## Context and Orientation

The Vault + ESO module will live alongside the existing OpenTofu modules in
`infra/modules`. The `cert_manager`, `traefik`, and `external_dns` modules
demonstrate the expected render/apply pattern, policy structure, and Terratest
conventions. Key paths and references:

- `infra/modules/cert_manager/` for the most recent module structure including
  split variable files, `rendered_manifests` outputs, and Open Policy Agent
  (OPA)/Conftest policies.
- `infra/modules/vault_appliance/` for the existing external Vault
  infrastructure (DigitalOcean droplets, load balancer, TLS, firewall).
- `.github/actions/bootstrap-vault-appliance/` for the Vault initialization
  action that provisions AppRole auth and KV v2 mount.
- `infra/testutil/` for shared Terratest helpers (`TerraformEnvVars`,
  `SetupTerraform`).
- `scripts/traefik-render-policy.sh` and `scripts/cert-manager-render-policy.sh`
  for render-policy automation patterns.
- `docs/declarative-tls-guide.md` for the overall GitOps patterns and secret
  management strategy using SOPS.
- `docs/cloud-native-ephemeral-previews.md` for the target architecture.
- `docs/opentofu-coding-standards.md` and
  `docs/opentofu-module-unit-testing-guide.md` for HCL rules and testing
  approach.
- `docs/ephemeral-previews-roadmap.md` for the roadmap entry that must be
  marked done when this module is complete.

Definitions used in this plan:

- **ESO**: External Secrets Operator — a Kubernetes operator that synchronizes
  secrets from external secret management systems into Kubernetes Secrets.
- **ClusterSecretStore**: A cluster-scoped ESO resource that defines how to
  connect to an external secret provider.
- **SecretStore**: A namespace-scoped ESO resource for external secret provider
  connections.
- **ExternalSecret**: An ESO resource that defines which secrets to fetch and
  how to store them.
- **AppRole**: A Vault authentication method designed for machine-to-machine
  authentication.
- **KV v2**: The versioned key-value secrets engine in Vault.
- **Vault Agent Injector**: An optional component that injects secrets into pods
  via sidecar containers.
- **Render mode**: OpenTofu emits manifests for Flux to apply via GitOps.
- **Apply mode**: OpenTofu applies resources directly to a live cluster.
- **Synchronization policy contract**: A set of outputs that downstream modules
  can consume to reference secret stores and create ExternalSecret resources.

## Plan of Work

### Phase 1: Design and Interface Definition

First, decide and document the Vault + ESO module interface. Use
`docs/vault-eso-module-design.md` to record decisions including:

- ESO chart version and repository source.
- Authentication method (AppRole vs Kubernetes auth).
- ClusterSecretStore vs namespace-scoped SecretStore approach.
- Vault Agent Injector enablement (optional component).
- Secret store naming conventions for the sync policy contract.
- Integration with the existing `bootstrap-vault-appliance` action outputs.

Update `docs/contents.md` to include the new design document, and ensure the
choice aligns with the existing Vault infrastructure.

### Phase 2: Module Scaffolding

Scaffold `infra/modules/vault_eso` with the same structure as the existing
modules:

- `main.tf` — module entry and locals
- `variables-core.tf` — core module inputs (namespace, mode, chart settings)
- `variables-vault.tf` — Vault connection settings
- `variables-eso.tf` — ESO-specific configuration
- `variables-agent.tf` — Vault Agent Injector settings (optional)
- `outputs.tf` — module outputs including sync policy contract
- `versions.tf` — provider requirements
- `manifests.tf` — rendered manifest construction
- `resources.tf` — apply-mode Kubernetes resources
- `.tflint.hcl` — linting configuration
- `README.md` — module documentation
- `examples/basic/` — apply-mode example
- `examples/render/` — render-mode example
- `policy/manifests/` — OPA policies for rendered manifests
- `policy/plan/` — OPA policies for plan output
- `tests/` — Terratest suites

Keep files under 400 lines by splitting logic as needed. Ensure at least one
module file starts with an HCL module header comment using `#` per repository
conventions.

### Phase 3: Module Implementation

Implement the module so it supports both `render` and `apply` modes. Build
`locals` that normalize input values, map defaults, merge Helm values, and
construct manifests for:

1. **ESO Namespace** — dedicated namespace for the operator.
2. **ESO HelmRepository** — source for the external-secrets chart.
3. **ESO HelmRelease** — the operator deployment with high-availability (HA)
   settings.
4. **ClusterSecretStore (KV v2)** — connects to Vault's KV secrets engine.
5. **ClusterSecretStore (PKI)** — optional; connects to Vault's PKI engine.
6. **AppRole authentication Secret** — stores role_id and secret_id for ESO.
7. **Vault Agent Injector HelmRelease** — optional; deploys the injector.
8. **PodDisruptionBudgets** — when replica counts exceed one.
9. **Kustomization manifest** — ties the GitOps tree together.

Render mode must return a `rendered_manifests` map keyed by the GitOps paths
under `platform/vault/` and `platform/sources/`.

### Phase 4: Input Variables

Define inputs with explicit `description`, `type`, and validation blocks.

**Required inputs:**

- `vault_address` — HTTPS endpoint of the external Vault appliance.
- `vault_ca_bundle_pem` — PEM-encoded CA certificate for Vault TLS validation.
- `approle_role_id` — AppRole role_id for ESO authentication.
- `approle_secret_id` — AppRole secret_id (sensitive).
- `kv_mount_path` — KV v2 mount path (default: `secret`).

**Optional inputs:**

- `mode` — `render` or `apply` (default: `render`).
- `namespace` — namespace for ESO (default: `external-secrets`).
- `create_namespace` — whether to create the namespace (default: `true`).
- `flux_namespace` — namespace for Flux sources (default: `flux-system`).
- `chart_version` — ESO chart version (pinned default).
- `replica_count` — ESO webhook/controller replicas (default: `2`).
- `pki_enabled` — enable PKI ClusterSecretStore (default: `false`).
- `pki_mount_path` — Vault PKI mount path.
- `agent_injector_enabled` — deploy Vault Agent Injector (default: `false`).
- `agent_injector_chart_version` — Vault Helm chart version for injector.
- `helm_values_override` — additional Helm values.
- `labels` — common labels to apply.
- `secret_store_name_kv` — name for the KV ClusterSecretStore.
- `secret_store_name_pki` — name for the PKI ClusterSecretStore.

Follow `docs/opentofu-coding-standards.md` (nullable handling, validations,
snake case, and `tofu fmt`).

### Phase 5: Output Variables

Expose outputs that downstream modules can consume (the sync policy contract):

- `namespace` — namespace where ESO is installed.
- `helm_release_name` — ESO HelmRelease name.
- `cluster_secret_store_kv_name` — name of the KV ClusterSecretStore.
- `cluster_secret_store_kv_ref` — reference object for the KV store.
- `cluster_secret_store_pki_name` — name of the PKI ClusterSecretStore (if
  enabled).
- `cluster_secret_store_pki_ref` — reference object for the PKI store.
- `vault_address` — Vault endpoint for documentation.
- `kv_mount_path` — KV mount path for ExternalSecret construction.
- `pki_mount_path` — PKI mount path (if enabled).
- `agent_injector_enabled` — whether the injector is deployed.
- `rendered_manifests` — map for render mode.

The sync policy contract object should bundle the secret store references and
mount paths, so workloads can construct ExternalSecret resources without
knowing the underlying Vault configuration.

### Phase 6: Examples

Add examples mirroring existing modules:

- **Apply-mode example** (`examples/basic/`): Include provider configuration and
  `kubeconfig_path` validation. Demonstrate full connectivity to a Vault
  instance with AppRole credentials.
- **Render-mode example** (`examples/render/`): Only depend on module inputs and
  export `rendered_manifests`. Duplicate module defaults in example variables
  so Terratest can override them.

### Phase 7: OPA/Conftest Policies

Create OPA/Conftest policies for both rendered manifests and plan output.

**Manifest policies should enforce:**

- Pinned chart versions (ESO and Vault Agent if enabled).
- Correct HelmRepository sourceRef.
- Namespace consistency across resources.
- ClusterSecretStore provider configuration validity.
- AppRole auth secret reference presence.
- PDB presence when replica counts exceed one.
- Vault address uses HTTPS scheme.

**Plan policies should:**

- Inspect `kubernetes_manifest` resources for ClusterSecretStore configuration.
- Assert Vault address uses HTTPS.
- Verify AppRole secret references are present.
- Warn if CA bundle is missing.
- Validate mount paths are non-empty.

### Phase 8: Terratest Coverage

Implement Terratest coverage under `infra/modules/vault_eso/tests/` using
`infra/testutil`. Include:

- **Happy-path tests** for render output and output wiring.
- **Unhappy-path tests** for missing or invalid variables.
- **Table-driven cases** for validation errors.
- **Policy tests** validating both accepted and rejected payloads.
- **Behavioural checks** running `tofu plan -detailed-exitcode` to guard against
  destructive or drift changes.
- **Apply-mode scenario** running `tofu apply` in a temporary workspace when
  environment variables are present, ensuring full create/destroy cycle.

### Phase 9: Makefile and Scripts

Update the Makefile to add:

- `vault-eso-test` target for Terratest execution.
- `vault-eso-policy` target for OPA policy validation.
- Include targets in `INFRA_TEST_TARGETS`.
- Add `tflint` coverage under `lint-infra`.

Create `scripts/vault-eso-render-policy.sh` helper modelled on existing
render-policy scripts.

### Phase 10: Documentation and Roadmap

Update `docs/ephemeral-previews-roadmap.md` to mark the Vault + ESO module
entry as done. Record any design decisions in the design document and update
`docs/contents.md` accordingly.

## Concrete Steps

All commands should be run from the repository root directory. Use a 300-second
timeout and capture logs with `tee` for any command with long output.

1. Create the module and policy scaffolding.

   ```bash
   mkdir -p infra/modules/vault_eso/{examples/basic,examples/render,policy/manifests,policy/plan,tests}
   ```

2. Draft the design document and update the documentation index.

   ```bash
   cat <<'DOC' > docs/vault-eso-module-design.md
   (Write the design decisions, interface details, and rationale here.)
   DOC
   ```

   (Update `docs/contents.md` to include the new design doc link.)

3. Implement module files and examples following the plan above. Keep module
   file sizes below 400 lines by splitting files as needed.

4. Generate provider lock files for the module and examples.

   ```bash
   timeout 300s bash -lc \
     'tofu -chdir=infra/modules/vault_eso init -input=false -no-color'
   timeout 300s bash -lc \
     'tofu -chdir=infra/modules/vault_eso/examples/basic init -input=false -no-color'
   timeout 300s bash -lc \
     'tofu -chdir=infra/modules/vault_eso/examples/render init -input=false -no-color'
   ```

5. Add Terratest suites and initialize the Go module for tests.

   ```bash
   timeout 300s bash -lc \
     'cd infra/modules/vault_eso/tests && go mod init nile-valley/infra/modules/vault_eso/tests'
   timeout 300s bash -lc \
     'cd infra/modules/vault_eso/tests && go mod tidy'
   ```

6. Add OPA policies and the render-policy script.

   ```bash
   touch scripts/vault-eso-render-policy.sh
   chmod +x scripts/vault-eso-render-policy.sh
   # (Model on existing render-policy scripts.)
   ```

7. Update Makefile targets and infra lint list to include vault-eso.

8. Run infra checks and policy suites with log capture.

   ```bash
   timeout 300s bash -lc \
     'set -o pipefail; make check-test-deps 2>&1 | tee /tmp/nile-valley-check-test-deps.log'
   timeout 300s bash -lc \
     'set -o pipefail; make vault-eso-test 2>&1 | tee /tmp/nile-valley-vault-eso-test.log'
   timeout 300s bash -lc \
     'set -o pipefail; make vault-eso-policy 2>&1 | tee /tmp/nile-valley-vault-eso-policy.log'
   ```

9. Run the apply-mode behavioural test in an ephemeral workspace when
   credentials are available. Record the environment variables used in the
   design doc.

   ```bash
   timeout 300s bash -lc 'set -o pipefail; \
     VAULT_ESO_KUBECONFIG_PATH=/path/to/kubeconfig \
     VAULT_ESO_VAULT_ADDRESS=https://vault.example.com \
     VAULT_ESO_APPROLE_ROLE_ID=<role_id> \
     VAULT_ESO_APPROLE_SECRET_ID=<secret_id> \
     VAULT_ESO_VAULT_CA_BUNDLE_PEM="$$(cat /path/to/vault-ca.pem)" \
     make vault-eso-test 2>&1 | tee /tmp/nile-valley-vault-eso-apply.log'
   ```

10. Validate any GitHub Actions files touched using action lint suite. Since
    this module does not directly modify GitHub Actions, this step may not apply
    unless integration tests are added.

    ```bash
    timeout 300s bash -lc \
      'set -o pipefail; make lint-actions 2>&1 | tee /tmp/nile-valley-lint-actions.log'
    ```

11. Run documentation formatting and linting after doc changes.

    ```bash
    timeout 300s bash -lc \
      'set -o pipefail; make fmt 2>&1 | tee /tmp/nile-valley-fmt.log'
    timeout 300s bash -lc \
      'set -o pipefail; make markdownlint 2>&1 | tee /tmp/nile-valley-markdownlint.log'
    ```

12. Run the required repository-wide gates before completion.

    ```bash
    timeout 300s bash -lc \
      'set -o pipefail; make check-fmt 2>&1 | tee /tmp/nile-valley-check-fmt.log'
    timeout 300s bash -lc \
    timeout 300s bash -lc \
      'set -o pipefail; make lint 2>&1 | tee /tmp/nile-valley-lint.log'
    timeout 300s bash -lc \
      'set -o pipefail; make test 2>&1 | tee /tmp/nile-valley-test.log'
    ```

## Validation and Acceptance

The work is complete when all of the following are true:

- `infra/modules/vault_eso` exists with module files, README, examples,
  policies, and Terratest suites matching repository conventions.
- Render mode produces a non-empty `rendered_manifests` map containing:
  - `platform/sources/external-secrets-repo.yaml`
  - `platform/vault/namespace.yaml`
  - `platform/vault/helmrelease.yaml`
  - `platform/vault/cluster-secret-store-kv.yaml`
  - `platform/vault/cluster-secret-store-pki.yaml` (when PKI enabled)
  - `platform/vault/approle-auth-secret.yaml`
  - `platform/vault/pdb-external-secrets.yaml` (when replicas > 1)
  - `platform/vault/vault-agent-injector-helmrelease.yaml` (when enabled)
  - `platform/vault/kustomization.yaml`
- Outputs include sync policy contract with secret store names, refs, and mount
  paths.
- `make vault-eso-test` and `make vault-eso-policy` pass locally and cover both
  happy and unhappy paths (invalid inputs, missing values, invalid endpoints,
  provider/API failures, and policy rejections).
- `tofu plan -detailed-exitcode` is exercised in tests or Makefile targets and
  handles exit code 2 as a drift signal.
- A successful apply-mode test runs in a temporary workspace when credentials
  are supplied, and the test cleans up after itself.
- The design decisions are recorded in the design document and linked from
  `docs/contents.md`.
- The Vault + ESO module entry in `docs/ephemeral-previews-roadmap.md` is marked
  done.

## Idempotence and Recovery

All steps should be re-runnable. The Terratest helper copies Terraform
configurations to temporary directories, so failed tests do not pollute the
working tree. If a `tofu` command fails, re-run it after fixing inputs; any
`tfplan.binary` or `plan.json` files created in temporary directories should be
removed by the test helpers or Makefile targets. If policy scripts leave
temporary directories, delete them and rerun the script.

## Artifacts and Notes

Expected `rendered_manifests` keys for render mode include (names may vary
based on decisions recorded in the design doc):

- `platform/sources/external-secrets-repo.yaml`
- `platform/vault/namespace.yaml`
- `platform/vault/helmrelease.yaml`
- `platform/vault/cluster-secret-store-kv.yaml`
- `platform/vault/cluster-secret-store-pki.yaml`
- `platform/vault/approle-auth-secret.yaml`
- `platform/vault/pdb-external-secrets-webhook.yaml`
- `platform/vault/pdb-external-secrets-controller.yaml`
- `platform/vault/vault-agent-injector-helmrelease.yaml`
- `platform/vault/kustomization.yaml`

**Sync Policy Contract Output Structure:**

```hcl
output "sync_policy_contract" {
  description = "Contract for downstream workloads to consume secrets"
  value = {
    kv_secret_store = {
      name       = local.cluster_secret_store_kv_name
      kind       = "ClusterSecretStore"
      mount_path = var.kv_mount_path
    }
    pki_secret_store = var.pki_enabled ? {
      name       = local.cluster_secret_store_pki_name
      kind       = "ClusterSecretStore"
      mount_path = var.pki_mount_path
    } : null
    vault_address = var.vault_address
  }
}
```

## Interfaces and Dependencies

The module must declare the following providers in
`infra/modules/vault_eso/versions.tf`:

- `opentofu/kubernetes` ~> 2.25.0
- `opentofu/helm` ~> 2.13.0

**Expected inputs (names can be refined but must be stable and documented):**

- `mode` (`render` or `apply`).
- `namespace`, `create_namespace`, `flux_namespace`,
  `flux_helm_repository_name`.
- Chart metadata (`chart_repository`, `chart_name`, `chart_version`).
- Vault settings (`vault_address`, `vault_ca_bundle_pem`, `kv_mount_path`,
  `pki_mount_path`, `pki_enabled`).
- AppRole settings (`approle_role_id`, `approle_secret_id`,
  `approle_auth_secret_name`).
- Agent injector settings (`agent_injector_enabled`,
  `agent_injector_chart_version`, `agent_injector_image_tag`).
- HA settings (`replica_count`, `pdb_min_available`).

**Expected outputs:**

- `namespace`, `helm_release_name`.
- `cluster_secret_store_kv_name`, `cluster_secret_store_kv_ref`.
- `cluster_secret_store_pki_name`, `cluster_secret_store_pki_ref`.
- `sync_policy_contract`.
- `agent_injector_enabled`.
- `rendered_manifests` map for render mode.

## Integration with Existing Infrastructure

The module integrates with:

1. **vault_appliance module** — provides the external Vault endpoint, CA
   certificate, and recovery keys.
2. **bootstrap-vault-appliance action** — provisions AppRole auth (role_id and
   secret_id) and KV v2 mount that ESO will consume.
3. **cert_manager module** — optional integration where cert-manager can issue
   certificates via Vault PKI through the ClusterIssuer, while ESO handles
   secret synchronization.
4. **nile-valley-infra-k8s action** — consumes the `rendered_manifests` output and
   commits to the GitOps repository.

## GitHub Actions Validation (if applicable)

If any GitHub Actions files are created or modified during implementation:

1. Validate with `yamllint` and `actionlint`:

   ```bash
   make lint-actions
   ```

2. Add local tests using `act` with `pytest` following
   `docs/local-validation-of-github-actions-with-act-and-pytest.md`.

## OpenTofu Verification Requirements

Per the user requirements, OpenTofu work must be verified by:

1. **Static checks**: `tofu fmt -check`, `tofu validate`, `tflint`.
2. **Unit-style tests**: Terratest with table-driven cases.
3. **Behavioural/E2E tests**: `tofu plan/apply` in ephemeral workspaces.
4. **Policy tests**: OPA/Conftest covering happy and unhappy paths.
5. **Drift detection**: `tofu plan -detailed-exitcode` handling.
6. **Edge cases**: Missing/invalid variables, provider failures, destructive
   change guards.

## Revision Note

- 2025-12-20: Initial draft of the Vault + ESO module ExecPlan. Defined scope,
  interface, integration points with existing Vault appliance infrastructure,
  and sync policy contract for downstream workloads.
