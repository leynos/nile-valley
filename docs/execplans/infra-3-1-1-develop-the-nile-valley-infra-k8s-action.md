# Develop the nile-valley-infra-k8s GitHub Action

This Execution Plan (ExecPlan) is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

Status: DRAFT

No `PLANS.md` file exists in this repository, so there is no additional plan
policy to follow.

## Purpose / big picture

Deliver the `nile-valley-infra-k8s` GitHub Action (Phase 3.1 of the ephemeral
previews roadmap) so that Kubernetes clusters and shared fixtures can be
assembled from the OpenTofu modules in the Nile Valley repository and
persisted in the `nile-valley-infra` GitOps repository for Flux Continuous
Delivery (FluxCD) to reconcile. Success is visible when:

1. The action can be invoked with cluster identifiers, Vault credentials, and
   GitOps repository details.
2. The action provisions the DigitalOcean Kubernetes Service (DOKS) cluster via
   the DOKS module (apply mode) if it does not exist, or validates the existing
   cluster.
3. The action renders Flux-ready manifests from all platform modules (traefik,
   cert-manager, external-dns, vault-eso, cnpg, valkey) in render mode.
4. The action commits the rendered manifests to `nile-valley-infra` with the
   expected GitOps layout (`clusters/<cluster>/`, `modules/`, `platform/*`).
5. Re-running the action is idempotent—it provisions or updates the cluster and
   reconciles the GitOps repository without duplicating resources.
6. OpenTofu state is persisted to a backend (e.g., DigitalOcean Spaces or
   Amazon Simple Storage Service (S3)) so that subsequent runs can detect and
   reconcile drift.
7. All tests pass: `make check-fmt`, `make lint`, and `make test`.

## Constraints

Hard invariants that must hold throughout implementation:

- The action must follow the composite action pattern established by
  `bootstrap-vault-appliance` (Python scripts invoked via `uv run`).
- Secrets must never appear in logs or OpenTofu state; all sensitive values must
  be masked via `::add-mask::`.
- The action must be idempotent; re-runs must not create duplicate commits or
  infrastructure resources.
- The DOKS module is invoked in apply mode to provision/update the cluster;
  platform modules are invoked in render mode for GitOps commit.
- OpenTofu state must be persisted to a remote backend (DigitalOcean Spaces or
  compatible S3) to enable drift detection and multi-run consistency.
- The GitOps repository layout must match the structure defined in
  `docs/ephemeral-previews-roadmap.md`.
- All files must adhere to the coding standards in `AGENTS.md` (max 400 lines,
  proper comments, en-GB-oxendict spelling).
- Destructive changes (cluster deletion, node pool removal) require explicit
  confirmation or must be prevented by default.

## Tolerances (exception triggers)

Thresholds that trigger escalation when breached:

- Scope: If implementation requires changes to more than 25 files or 2000 lines
  of code (net), stop and escalate.
- Interface: If any existing module's public interface must change (breaking
  change to inputs/outputs), stop and escalate.
- Dependencies: If a new external Python or Go dependency is required beyond
  those already used in similar scripts, stop and escalate.
- Iterations: If tests still fail after 5 fix attempts, stop and escalate.
- Ambiguity: If multiple valid interpretations exist for GitOps layout or module
  wiring, present options with trade-offs before proceeding.

## Risks

- Risk: Vault authentication may fail if AppRole credentials are not correctly
  provisioned.
  Severity: high
  Likelihood: low
  Mitigation: The `bootstrap-vault-appliance` action already provisions the
  AppRole; reuse the same credential flow and add validation tests.

- Risk: OpenTofu modules may produce conflicting manifest paths.
  Severity: medium
  Likelihood: low
  Mitigation: Create a platform_render orchestration module that merges outputs
  and validates path uniqueness; add Conftest policies.

- Risk: GitOps commit conflicts if multiple action runs target the same branch
  concurrently.
  Severity: medium
  Likelihood: medium
  Mitigation: Document that the action should run serially per branch; consider
  adding a lock mechanism or retry logic in future iterations.

- Risk: End-to-end (E2E) tests require real Vault, DigitalOcean, and GitOps
  credentials.
  Severity: low
  Likelihood: high
  Mitigation: Provide mock modes for continuous integration (CI); run full E2E
  tests only in protected environments with explicit opt-in.

- Risk: Cluster provisioning may fail due to DigitalOcean API rate limits or
  resource quota exhaustion.
  Severity: high
  Likelihood: low
  Mitigation: Add retry logic with exponential backoff; document quota
  requirements; surface clear error messages.

- Risk: OpenTofu state may become corrupted or lost if the backend is
  unavailable.
  Severity: high
  Likelihood: low
  Mitigation: Use DigitalOcean Spaces with versioning enabled; implement state
  locking to prevent concurrent modifications.

- Risk: Accidental cluster deletion if action is misconfigured or state is
  corrupted.
  Severity: critical
  Likelihood: low
  Mitigation: Use `prevent_destroy` lifecycle rule on the cluster resource;
  require explicit `allow_destroy` input for teardown operations.

## Progress

- [x] (2026-01-16) Draft the initial ExecPlan and record design decisions.
- [x] (2026-01-16) Configure the OpenTofu backend (DigitalOcean Spaces) for
  state management.
- [x] (2026-01-16) Create the cluster provisioning OpenTofu configuration for
  DOKS module invocation.
- [x] (2026-01-16) Create the platform_render OpenTofu orchestration module.
  Note: Valkey excluded due to provider version incompatibility.
- [x] (2026-01-16) Implement Python helper scripts (prepare, provision, render,
  commit, publish). Created: `_infra_k8s.py`, `prepare_infra_k8s_inputs.py`,
  `provision_cluster.py`, `render_platform_manifests.py`,
  `commit_gitops_manifests.py`, `publish_infra_k8s_outputs.py`.
- [x] (2026-01-16) Create the composite action definition (action.yml).
  Created: `.github/actions/nile-valley-infra-k8s/action.yml`.
- [x] (2026-01-16) Write structural tests for action.yml.
  Created: `scripts/tests/test_infra_k8s_action_manifest.py` with 12 tests.
- [x] (2026-01-16) Add Terratest coverage for platform_render module.
  Created: `infra/modules/platform_render/tests/platform_render_test.go`.
- [x] (2026-01-16) Update Makefile targets. Added `platform-render-test` target.
- [x] (2026-01-16) Run repository-wide gates (`make check-fmt`, `make lint`,
  `make scripts-test`). All gates pass.
- [ ] (Pending) Add Open Policy Agent (OPA)/Conftest policies for GitOps
  layout and infrastructure validation.
- [ ] (Pending) Write unit tests for Python scripts using cmd-mox.
- [ ] (Pending) Create documentation (design docs, README).
- [ ] (Pending) Mark the relevant roadmap entry as done.

## Surprises & discoveries

- Observation: The valkey module uses different provider versions (helm
  ~> 3.1.1, kubernetes ~> 3.0.1) than other platform modules (~> 2.13.0 and
  ~> 2.25.0).
  Evidence: tofu init failed with "no available releases match the given
  constraints" when attempting to include valkey in platform_render.
  Impact: Valkey is temporarily excluded from platform_render until provider
  versions are unified across all modules. A future task should upgrade all
  modules to helm 3.x and kubernetes 3.x.

## Decision log

- Decision: Exclude valkey from platform_render module until provider versions
  are unified.
  Rationale: The valkey module requires helm ~> 3.1.1 and kubernetes ~> 3.0.1,
  while other modules use ~> 2.13.0 and ~> 2.25.0 respectively. OpenTofu cannot
  resolve conflicting provider versions. Upgrading all modules to 3.x would
  require testing and potential code changes across the codebase.
  Date/Author: 2026-01-16 / Claude.

Initial anticipated decisions below:

- Decision: (Pending) Use composite action pattern with Python scripts.
  Rationale: Matches the established `bootstrap-vault-appliance` pattern;
  enables pytest/cmd-mox testing without container builds.
  Date/Author: Pending.

- Decision: (Pending) Use DigitalOcean Spaces as the OpenTofu state backend.
  Rationale: Provides S3-compatible storage within DigitalOcean ecosystem;
  supports versioning and state locking via DynamoDB-compatible API.
  Date/Author: Pending.

- Decision: (Pending) Provision clusters via the DOKS module in apply mode before
  rendering platform fixtures.
  Rationale: Ensures the cluster exists and is healthy before attempting to
  configure platform services; enables retrieval of kubeconfig for subsequent
  FluxCD bootstrap.
  Date/Author: Pending.

- Decision: (Pending) Create a platform_render OpenTofu module to orchestrate
  all platform modules in render mode.
  Rationale: Centralizes module wiring logic; enables validation of merged
  outputs before committing to GitOps.
  Date/Author: Pending.

- Decision: (Pending) Support feature flags for enabling/disabling individual
  platform components.
  Rationale: Not all clusters require all services; ephemeral previews may use a
  subset.
  Date/Author: Pending.

- Decision: (Pending) Sync infra/modules/ to nile-valley-infra/modules/ as
  part of the commit workflow.
  Rationale: Keeps the GitOps repository self-contained; enables FluxCD to
  reference modules for cluster-specific overrides.
  Date/Author: Pending.

- Decision: (Pending) Use `prevent_destroy` lifecycle rule on cluster resources.
  Rationale: Prevents accidental cluster deletion; requires explicit action
  input to enable teardown operations.
  Date/Author: Pending.

- Decision: (Pending) Store kubeconfig in Vault after cluster provisioning.
  Rationale: Enables secure retrieval by subsequent actions and local
  development; avoids exposing credentials in action outputs.
  Date/Author: Pending.

## Outcomes & retrospective

(To be completed when work is finished.)

## Context and orientation

The `nile-valley-infra-k8s` action is part of Phase 3.1 of the ephemeral previews
roadmap. It consumes the OpenTofu modules created in Phase 2.3 (traefik,
cert-manager, external-dns, vault-eso, cnpg, valkey) and orchestrates them to
produce a coherent set of Flux-ready manifests.

Key paths and references:

- `infra/modules/traefik/` — reference module with render mode support and
  `rendered_manifests` output.
- `infra/modules/cert_manager/` — reference module with comprehensive variable
  validation and Terratest coverage.
- `infra/modules/vault_eso/` — Vault + ESO module providing the sync policy
  contract for secrets.
- `.github/actions/bootstrap-vault-appliance/` — reference composite action with
  Python helper scripts.
- `scripts/prepare_bootstrap_inputs.py` — reference for input resolution and
  GITHUB_ENV export.
- `scripts/tests/test_bootstrap_vault_action_manifest.py` — reference for
  structural action tests.
- `infra/testutil/` — shared Terratest helpers.
- `docs/cloud-native-ephemeral-previews.md` — target architecture.
- `docs/ephemeral-previews-roadmap.md` — roadmap entry to mark as done.
- `docs/local-validation-of-github-actions-with-act-and-pytest.md` — guidance
  for action testing.
- `docs/opentofu-coding-standards.md` — HashiCorp Configuration Language (HCL)
  coding rules.
- `docs/opentofu-module-unit-testing-guide.md` — testing approach.

Definitions used in this plan:

- **Render mode**: OpenTofu emits manifests as a map output for Flux to apply
  via GitOps, without directly applying resources to a cluster.
- **Apply mode**: OpenTofu applies resources directly to a live cluster.
- **GitOps repository**: The `nile-valley-infra` repository that FluxCD monitors
  and reconciles.
- **Platform modules**: traefik, cert-manager, external-dns, vault-eso, cnpg,
  valkey.
- **platform_render module**: New orchestration module that wires all platform
  modules together in render mode.
- **Composite action**: A GitHub Action defined using `runs: composite` with
  shell steps.

## Plan of Work

### Phase 1: OpenTofu State Backend Configuration

Configure DigitalOcean Spaces as the OpenTofu state backend:

1. Create a reusable backend configuration file
   (`infra/backend-config/spaces.tfbackend`) that can be passed to `tofu init`.
2. Document the required Spaces bucket and access credentials.
3. Configure state locking using a DynamoDB-compatible lock table (or document
   alternative approach if not using DynamoDB).
4. Ensure the backend supports workspace isolation for multiple clusters.

Files to create:

- `infra/backend-config/spaces.tfbackend` — backend configuration template.
- `docs/opentofu-state-backend.md` — documentation for state management.

### Phase 2: Cluster Provisioning Configuration

Create `infra/clusters/nile-valley-infra-k8s/` as the OpenTofu root configuration
that provisions clusters via the DOKS module:

1. Define the root configuration that invokes the DOKS module.
2. Add the fluxcd module to bootstrap FluxCD on the provisioned cluster.
3. Configure backend to use workspace-per-cluster isolation.
4. Add outputs for cluster ID, API endpoint, and kubeconfig retrieval.
5. Implement `prevent_destroy` lifecycle rules on the cluster resource.

Files to create:

- `infra/clusters/nile-valley-infra-k8s/main.tf` — root configuration.
- `infra/clusters/nile-valley-infra-k8s/variables.tf` — cluster inputs.
- `infra/clusters/nile-valley-infra-k8s/outputs.tf` — cluster outputs.
- `infra/clusters/nile-valley-infra-k8s/versions.tf` — provider requirements.
- `infra/clusters/nile-valley-infra-k8s/backend.tf` — backend configuration.
- `infra/clusters/nile-valley-infra-k8s/.tflint.hcl` — symlink to the shared
  `infra/.tflint.hcl` linting configuration.

### Phase 3: Platform Render Orchestration Module

Create `infra/modules/platform_render/` to wire all platform modules together in
render mode. This module:

1. Accepts cluster/environment identifiers, domain, ACME email, and feature
   flags.
2. Invokes each enabled platform module with `mode = "render"`.
3. Merges all `rendered_manifests` outputs into a single map.
4. Validates that there are no path collisions.
5. Generates a root Kustomization for the cluster.

Files to create:

- `infra/modules/platform_render/main.tf` — module entry with conditional
  module invocations.
- `infra/modules/platform_render/variables.tf` — cluster config and feature
  flags.
- `infra/modules/platform_render/outputs.tf` — merged `rendered_manifests`.
- `infra/modules/platform_render/versions.tf` — provider requirements (no
  providers needed; pure HCL).
- `infra/modules/platform_render/examples/full/main.tf` — example with all
  modules enabled.
- `infra/modules/platform_render/tests/` — Terratest suites.
- `infra/modules/platform_render/policy/` — OPA policies for path collision
  detection.
- `infra/modules/platform_render/README.md` — module documentation.
- `infra/modules/platform_render/.tflint.hcl` — symlink to the shared
  `infra/.tflint.hcl` linting configuration.

### Phase 4: Python Helper Scripts

Create Python scripts following the `bootstrap-vault-appliance` pattern:

1. **`scripts/prepare_infra_k8s_inputs.py`**
   - Resolve and validate action inputs from environment variables.
   - Authenticate to Vault using AppRole credentials.
   - Retrieve required secrets (Cloudflare API token, DigitalOcean token,
     Spaces credentials for state backend).
   - Export resolved values to `$GITHUB_ENV` and mask secrets.

2. **`scripts/provision_cluster.py`**
   - Configure OpenTofu backend with Spaces credentials.
   - Run `tofu init` with backend configuration.
   - Select or create the workspace for the target cluster.
   - Run `tofu plan` to detect drift and preview changes.
   - Run `tofu apply -auto-approve` to provision/update the cluster.
   - Extract cluster outputs (ID, endpoint) and kubeconfig.
   - Store kubeconfig in Vault for subsequent retrieval.
   - Export cluster metadata to `$GITHUB_ENV`.

3. **`scripts/render_platform_manifests.py`**
   - Create a temporary workspace with the platform_render module.
   - Run `tofu init` and `tofu apply -auto-approve`.
   - Extract `rendered_manifests` output via `tofu output -json`.
   - Write manifests to `$RENDER_OUTPUT_DIR`.

4. **`scripts/commit_gitops_manifests.py`**
   - Clone the `nile-valley-infra` GitOps repository.
   - Sync `infra/modules/` to `modules/` in the GitOps repository.
   - Copy rendered manifests to `clusters/<cluster>/` and `platform/`.
   - Check for changes; commit and push only if there are differences.
   - Export commit SHA to `$GITHUB_ENV`.

5. **`scripts/publish_infra_k8s_outputs.py`**
   - Read computed values from environment.
   - Write outputs to `$GITHUB_OUTPUT`.
   - Final secret masking pass.

6. **`scripts/_infra_k8s.py`**
   - Shared utilities for OpenTofu invocation, backend configuration, and
     manifest handling.

### Phase 5: Composite Action Definition

Create `.github/actions/nile-valley-infra-k8s/action.yml`:

**Inputs:**

- `cluster_name` (required) — name of the target cluster.
- `environment` (required) — logical environment (preview, staging, production).
- `region` (required) — DigitalOcean region.
- `kubernetes_version` (optional) — DOKS Kubernetes version.
- `node_pools` (optional) — JSON-encoded node pool configuration.
- `gitops_repository` (required) — target GitOps repository (owner/repo).
- `gitops_branch` (optional, default: main) — branch to commit to.
- `gitops_token` (required) — GitHub token with write access.
- `vault_address` (required) — Vault HTTPS endpoint.
- `vault_role_id` (required) — AppRole role_id.
- `vault_secret_id` (required) — AppRole secret_id.
- `vault_ca_certificate` (optional) — CA certificate for Vault TLS.
- `digitalocean_token` (required) — DigitalOcean API token.
- `spaces_access_key` (required) — Spaces access key for state backend.
- `spaces_secret_key` (required) — Spaces secret key for state backend.
- `domain` (required) — base domain for cluster services.
- `acme_email` (required) — email for ACME registration.
- `enable_traefik` (optional, default: true) — deploy Traefik.
- `enable_cert_manager` (optional, default: true) — deploy cert-manager.
- `enable_external_dns` (optional, default: true) — deploy external-dns.
- `enable_vault_eso` (optional, default: true) — deploy Vault + ESO.
- `enable_cnpg` (optional, default: true) — deploy CloudNativePG.
- `enable_valkey` (optional, default: true) — deploy Valkey.
- `allow_destroy` (optional, default: false) — allow cluster destruction.
- `dry_run` (optional, default: false) — plan without applying/committing.

**Outputs:**

- `cluster_name` — configured cluster name.
- `cluster_id` — DigitalOcean cluster ID.
- `cluster_endpoint` — Kubernetes API endpoint.
- `gitops_commit_sha` — commit SHA (empty in dry-run mode).
- `rendered_manifest_count` — number of manifests rendered.

**Steps:**

1. Install uv (astral-sh/setup-uv).
2. Install OpenTofu (opentofu/setup-opentofu).
3. Install doctl (digitalocean/action-doctl).
4. Prepare inputs and retrieve secrets (uv run prepare_infra_k8s_inputs.py).
5. Provision cluster (uv run provision_cluster.py) — runs tofu plan/apply.
6. Render platform manifests (uv run render_platform_manifests.py).
7. Commit to GitOps repository (uv run commit_gitops_manifests.py) —
   conditional on `dry_run != 'true'`.
8. Publish outputs (uv run publish_infra_k8s_outputs.py).

### Phase 6: Tests

**Structural tests** (`scripts/tests/test_infra_k8s_action_manifest.py`):

- Validate action.yml structure using yaml.safe_load.
- Assert required inputs are marked as required.
- Assert outputs are wired to the publish step.
- Assert provisioning and render steps invoke the correct scripts.

**Python unit tests** (`scripts/tests/test_*.py`):

- Use pytest and cmd-mox to mock `tofu`, `git`, `vault`, and `doctl` commands.
- Test input validation, Vault authentication, cluster provisioning, manifest
  rendering, and GitOps commit logic.
- Cover happy paths (valid inputs, successful provisioning/renders) and unhappy
  paths (invalid inputs, authentication failures, provisioning failures,
  command failures).
- Test `prevent_destroy` behaviour and `allow_destroy` override.

**Terratest suites:**

For `infra/clusters/nile-valley-infra-k8s/tests/`:

- Test cluster provisioning with mocked DigitalOcean provider.
- Test `tofu plan -detailed-exitcode` for drift detection.
- Test `prevent_destroy` lifecycle rule enforcement.
- Test workspace isolation for multiple clusters.

For `infra/modules/platform_render/tests/`:

- Test render mode produces expected manifest keys.
- Test feature flags conditionally include/exclude modules.
- Test path collision detection when modules produce conflicting paths.
- Use table-driven test cases for validation errors.

**OPA/Conftest policies:**

For `infra/clusters/nile-valley-infra-k8s/policy/`:

- Validate cluster configuration (region, version, node pools).
- Ensure `prevent_destroy` is present on cluster resources.
- Validate state backend configuration.

For `infra/modules/platform_render/policy/`:

- Validate all HelmReleases reference valid HelmRepositories.
- Validate Kustomization resources reference existing files.
- Validate no duplicate paths in merged manifests.
- Test both accepted and rejected payloads.

**Action validation:**

- Validate action.yml with `yamllint` and `actionlint` via `make lint-actions`.

### Phase 7: Makefile Targets

Add the following targets:

- `cluster-provision-test` — run Terratest for cluster provisioning
  configuration.
- `cluster-provision-policy` — run Conftest policies for cluster provisioning.
- `platform-render-test` — run Terratest for platform_render module.
- `platform-render-policy` — run Conftest policies for platform_render module.
- Add all four targets to `INFRA_TEST_TARGETS`.
- Add `tflint` coverage for platform_render and cluster provisioning to
  `lint-infra`.

### Phase 8: Documentation and Roadmap

- Create `docs/nile-valley-infra-k8s-action-design.md` with design decisions.
- Create `docs/opentofu-state-backend.md` with state management documentation.
- Update `docs/contents.md` to include the new design documents.
- Update `docs/ephemeral-previews-roadmap.md` to mark the `nile-valley-infra-k8s`
  entry as done.
- Create `.github/actions/nile-valley-infra-k8s/README.md` with usage examples.

## Concrete Steps

All commands should be run from the repository root directory. Use a 300-second
timeout for long-running commands.

### Step 1: Create the backend configuration

    mkdir -p infra/backend-config
    cat > infra/backend-config/spaces.tfbackend <<'EOF'
    bucket   = "nile-valley-tofu-state"
    key      = "clusters/${cluster_name}/terraform.tfstate"
    region   = "nyc3"
    endpoint = "nyc3.digitaloceanspaces.com"
    EOF

### Step 2: Create the cluster provisioning configuration

    mkdir -p infra/clusters/nile-valley-infra-k8s/{tests,policy}

Create `infra/clusters/nile-valley-infra-k8s/main.tf`:

    # Nile Valley Infrastructure Kubernetes Cluster Provisioning
    #
    # Provisions a DigitalOcean Kubernetes cluster and bootstraps FluxCD.

    terraform {
      backend "s3" {
        # Configured via -backend-config at init time
      }
    }

    module "doks" {
      source             = "../../modules/doks"
      cluster_name       = var.cluster_name
      region             = var.region
      kubernetes_version = var.kubernetes_version
      node_pools         = var.node_pools

      lifecycle {
        prevent_destroy = true
      }
    }

    module "fluxcd" {
      source               = "../../modules/fluxcd"
      kubeconfig_path      = local.kubeconfig_path
      git_repository_url   = var.git_repository_url
      git_repository_path  = var.git_repository_path
      git_repository_branch = var.git_repository_branch
    }

### Step 3: Create the platform_render module scaffolding

    mkdir -p infra/modules/platform_render/{examples/full,tests,policy/manifests}

### Step 4: Implement the platform_render module

Create `infra/modules/platform_render/main.tf`:

    # Platform Render Orchestration Module
    #
    # Wires all platform modules together in render mode and merges their
    # rendered_manifests outputs into a single map for GitOps commit.

    locals {
      # Merge all enabled modules' rendered_manifests
      all_manifests = merge(
        var.enable_traefik ? module.traefik[0].rendered_manifests : {},
        var.enable_cert_manager ? module.cert_manager[0].rendered_manifests : {},
        var.enable_external_dns ? module.external_dns[0].rendered_manifests : {},
        var.enable_vault_eso ? module.vault_eso[0].rendered_manifests : {},
        var.enable_cnpg ? module.cnpg[0].rendered_manifests : {},
        var.enable_valkey ? module.valkey[0].rendered_manifests : {},
      )
    }

    module "traefik" {
      count  = var.enable_traefik ? 1 : 0
      source = "../traefik"
      mode   = "render"
      # ... required variables
    }

    # ... similar blocks for other modules

Create variables.tf, outputs.tf, versions.tf, and examples following existing
module patterns.

### Step 5: Generate provider lock files

    timeout 300s bash -lc \
      'tofu -chdir=infra/clusters/nile-valley-infra-k8s init -input=false -no-color -backend=false'
    timeout 300s bash -lc \
      'tofu -chdir=infra/modules/platform_render/examples/full init -input=false -no-color'

### Step 6: Create Python helper scripts

Create `scripts/prepare_infra_k8s_inputs.py`:

    #!/usr/bin/env -S uv run python
    # /// script
    # requires-python = ">=3.13"
    # dependencies = ["cyclopts>=2.9", "plumbum"]
    # ///
    """Prepare nile-valley-infra-k8s inputs and retrieve secrets from Vault."""

    # (Implementation follows bootstrap-vault-appliance pattern)

Create `scripts/provision_cluster.py`:

    #!/usr/bin/env -S uv run python
    # /// script
    # requires-python = ">=3.13"
    # dependencies = ["cyclopts>=2.9", "plumbum"]
    # ///
    """Provision or update the Kubernetes cluster via OpenTofu."""

    # Key steps:
    # 1. Configure backend with Spaces credentials
    # 2. Run tofu init with backend-config
    # 3. Select or create workspace
    # 4. Run tofu plan -detailed-exitcode
    # 5. Run tofu apply -auto-approve
    # 6. Extract outputs and kubeconfig
    # 7. Store kubeconfig in Vault

Create similar scripts for render, commit, and publish phases.

### Step 7: Add Terratest coverage

    cd infra/clusters/nile-valley-infra-k8s/tests && \
      go mod init nile-valley/infra/clusters/nile-valley-infra-k8s/tests && \
      go mod tidy

    cd infra/modules/platform_render/tests && \
      go mod init nile-valley/infra/modules/platform_render/tests && \
      go mod tidy

### Step 8: Create the composite action

Create `.github/actions/nile-valley-infra-k8s/action.yml` following the structure
defined in Phase 5.

### Step 9: Write structural tests

Create `scripts/tests/test_infra_k8s_action_manifest.py` following the pattern
from `test_bootstrap_vault_action_manifest.py`.

### Step 10: Update Makefile

Add targets to Makefile:

    cluster-provision-test:
    	tofu fmt -check infra/clusters/nile-valley-infra-k8s
    	tofu -chdir=infra/clusters/nile-valley-infra-k8s init -backend=false
    	tofu -chdir=infra/clusters/nile-valley-infra-k8s validate
    	cd infra/clusters/nile-valley-infra-k8s && tflint --init && tflint --config .tflint.hcl
    	cd infra/clusters/nile-valley-infra-k8s/tests && $(GO_TEST_ENV) go test -v
    	$(MAKE) cluster-provision-policy

    cluster-provision-policy: conftest tofu
    	conftest test infra/clusters/nile-valley-infra-k8s --policy infra/clusters/nile-valley-infra-k8s/policy --ignore ".terraform"

    platform-render-test:
    	tofu fmt -check infra/modules/platform_render
    	tofu -chdir=infra/modules/platform_render/examples/full init
    	tofu -chdir=infra/modules/platform_render/examples/full validate
    	cd infra/modules/platform_render && tflint --init && tflint --config .tflint.hcl
    	cd infra/modules/platform_render/tests && $(GO_TEST_ENV) go test -v
    	$(MAKE) platform-render-policy

    platform-render-policy: conftest tofu
    	conftest test infra/modules/platform_render --policy infra/modules/platform_render/policy --ignore ".terraform"

Add all targets to `INFRA_TEST_TARGETS`.

### Step 11: Run validation

    timeout 300s bash -lc \
      'set -o pipefail; make lint-actions 2>&1 | tee /tmp/nile-valley-lint-actions.log'

    timeout 300s bash -lc \
      'set -o pipefail; make scripts-test 2>&1 | tee /tmp/nile-valley-scripts-test.log'

    timeout 300s bash -lc \
      'set -o pipefail; make cluster-provision-test 2>&1 | tee /tmp/nile-valley-cluster-provision-test.log'

    timeout 300s bash -lc \
      'set -o pipefail; make platform-render-test 2>&1 | tee /tmp/nile-valley-platform-render-test.log'

### Step 12: Run repository-wide gates

    timeout 300s bash -lc \
      'set -o pipefail; make check-fmt 2>&1 | tee /tmp/nile-valley-check-fmt.log'
    timeout 300s bash -lc \
    timeout 300s bash -lc \
      'set -o pipefail; make lint 2>&1 | tee /tmp/nile-valley-lint.log'
    timeout 300s bash -lc \
      'set -o pipefail; make test 2>&1 | tee /tmp/nile-valley-test.log'

### Step 13: Update roadmap

Edit `docs/ephemeral-previews-roadmap.md` to mark the `nile-valley-infra-k8s`
action entry as done:

    - [x] **Develop the `nile-valley-infra-k8s` action**

## Validation and Acceptance

The work is complete when all of the following are true:

1. `.github/actions/nile-valley-infra-k8s/action.yml` exists and passes
   `make lint-actions`.

2. `infra/clusters/nile-valley-infra-k8s/` exists with root configuration,
   variables, outputs, backend configuration, policies, and Terratest suites.

3. `infra/modules/platform_render/` exists with module files, README, examples,
   policies, and Terratest suites matching repository conventions.

4. `infra/backend-config/spaces.tfbackend` exists with the state backend
   configuration template.

5. Cluster provisioning:
   - The DOKS module can be invoked to create/update clusters.
   - `prevent_destroy` lifecycle rule is enforced on cluster resources.
   - `allow_destroy` input overrides the protection when explicitly set.
   - Kubeconfig is stored in Vault after provisioning.

6. Render mode produces a non-empty `rendered_manifests` map containing paths
   for all enabled platform components:
   - `platform/sources/*.yaml` — HelmRepository definitions.
   - `platform/traefik/*.yaml` — Traefik manifests.
   - `platform/cert-manager/*.yaml` — cert-manager manifests.
   - `platform/external-dns/*.yaml` — external-dns manifests.
   - `platform/vault/*.yaml` — Vault + ESO manifests.
   - `platform/databases/*.yaml` — CloudNativePG manifests.
   - `platform/redis/*.yaml` — Valkey manifests.

7. Structural tests for action.yml pass via `make scripts-test`.

8. Python unit tests pass with cmd-mox mocking, covering:
   - Happy paths (valid inputs, successful Vault auth, successful
     provisioning/render).
   - Unhappy paths (missing inputs, Vault auth failure, provisioning failures,
     OpenTofu errors).
   - `prevent_destroy` and `allow_destroy` behaviour.

9. Terratest suites pass:
   - `make cluster-provision-test` for cluster provisioning.
   - `make platform-render-test` for platform rendering.

10. OPA/Conftest policies pass:
    - `make cluster-provision-policy` for infrastructure policies.
    - `make platform-render-policy` for GitOps layout policies.

11. `tofu plan -detailed-exitcode` is exercised in tests and handles exit code 2
    as expected.

12. The design decisions are recorded in
    `docs/nile-valley-infra-k8s-action-design.md` and linked from
    `docs/contents.md`.

13. State backend documentation exists in `docs/opentofu-state-backend.md`.

14. The `nile-valley-infra-k8s` entry in `docs/ephemeral-previews-roadmap.md` is
    marked done.

    succeed.

## Idempotence and Recovery

All steps should be re-runnable:

- **Cluster provisioning** is idempotent: `tofu apply` converges to the desired
  state without creating duplicates. The state backend ensures consistency
  across runs.
- **State recovery**: If state becomes corrupted, use `tofu import` to
  re-associate existing resources, or restore from Spaces versioned backup.
- The platform_render module uses pure HCL with no side effects in render mode.
- Terratest copies configurations to temporary directories, so failed tests do
  not pollute the working tree.
- Python scripts read inputs from environment variables and write outputs to
  standard GitHub Actions mechanisms (`$GITHUB_ENV`, `$GITHUB_OUTPUT`).
- The commit script checks for changes before committing; re-runs with no
  changes produce no new commits.
- If a step fails, fix the issue and re-run from that step; no cleanup is
  required for platform_render. For cluster provisioning failures, verify state
  is consistent before retrying.

## Artifacts and Notes

**Expected GitOps repository layout after action runs:**

    nile-valley-infra/
    ├── clusters/
    │   └── <cluster_name>/
    │       └── kustomization.yaml
    ├── modules/
    │   ├── traefik/
    │   ├── cert_manager/
    │   ├── external_dns/
    │   ├── vault_eso/
    │   ├── cnpg/
    │   └── valkey/
    └── platform/
        ├── sources/
        │   ├── traefik-repo.yaml
        │   ├── cert-manager-repo.yaml
        │   ├── external-dns-repo.yaml
        │   ├── external-secrets-repo.yaml
        │   ├── cnpg-repo.yaml
        │   └── valkey-repo.yaml
        ├── traefik/
        │   ├── namespace.yaml
        │   ├── helmrelease.yaml
        │   ├── cluster-issuer.yaml
        │   ├── crds/
        │   └── kustomization.yaml
        ├── cert-manager/
        │   └── ...
        ├── external-dns/
        │   └── ...
        ├── vault/
        │   └── ...
        ├── databases/
        │   └── ...
        └── redis/
            └── ...

**Python script dependencies:**

- `cyclopts>=2.9` — CLI argument parsing.
- `plumbum` — subprocess management.

**Test dependencies:**

- `pytest` — test framework.
- `cmd-mox==0.2.0` — command mocking.
- `pyyaml` — YAML parsing for structural tests.

## Interfaces and Dependencies

**Platform render module inputs:**

- `cluster_name` (string, required) — cluster identifier.
- `environment` (string, required) — logical environment.
- `domain` (string, required) — base domain for services.
- `acme_email` (string, required) — ACME registration email.
- `enable_traefik` (bool, default: true) — include Traefik.
- `enable_cert_manager` (bool, default: true) — include cert-manager.
- `enable_external_dns` (bool, default: true) — include external-dns.
- `enable_vault_eso` (bool, default: true) — include Vault + ESO.
- `enable_cnpg` (bool, default: true) — include CloudNativePG.
- `enable_valkey` (bool, default: true) — include Valkey.
- Additional variables passed through to child modules (Vault address, API
  tokens, etc.).

**Platform render module outputs:**

- `rendered_manifests` (map of string to string) — GitOps paths to YAML content.
- `enabled_components` (list of string) — names of enabled components.
- `manifest_count` (number) — total number of manifests rendered.

## GitHub Actions Validation

The action must be validated using:

1. `yamllint` — YAML syntax validation.
2. `actionlint` — GitHub Actions-specific linting.
3. `action-validator` — action metadata validation.

These are run via `make lint-actions`.

## OpenTofu Verification Requirements

Per the user requirements, OpenTofu work must be verified by:

1. **Static checks**: `tofu fmt -check`, `tofu validate`, `tflint`.
2. **Unit-style tests**: Terratest with table-driven cases.
3. **Behavioural/E2E tests**: `tofu plan` in ephemeral workspaces.
4. **Policy tests**: OPA/Conftest covering happy and unhappy paths.
5. **Drift detection**: `tofu plan -detailed-exitcode` handling.
6. **Edge cases**: Missing/invalid variables, validation errors.

Note: Since the platform_render module operates in render mode only (no cloud
providers, no apply), E2E tests focus on validating the rendered output rather
than deploying infrastructure.

## Revision Note

- 2026-01-16: Initial draft of the nile-valley-infra-k8s action ExecPlan. Defined
  scope, action interface, platform_render orchestration module, Python helper
  scripts, testing strategy, and GitOps layout.
