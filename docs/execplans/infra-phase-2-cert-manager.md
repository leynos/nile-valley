# Cert-manager module plan for core cluster services

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

No `PLANS.md` file exists in this repository, so there is no additional plan
policy to follow.

## Purpose / Big Picture

Deliver the Phase 2.3 cert-manager module so the `nile-valley-infra-k8s` action
can render Flux-ready manifests into `nile-valley-infra` and converge TLS issuance
on every run. Success is visible when the new OpenTofu module can render a
`platform/cert-manager` tree containing the cert-manager HelmRelease and
ClusterIssuers for ACME (Automated Certificate Management Environment) and
Vault, and when its outputs expose issuer names, secret references, and CA
bundle material for downstream modules.

## Progress

- [x] (2025-12-19 19:10Z) Drafted the initial ExecPlan for the cert-manager
  module.
- [x] (2025-12-19 20:25Z) Confirmed the module interface and recorded decisions
  in `docs/cert-manager-module-design.md`.
- [x] (2025-12-19 20:45Z) Implemented module files, examples, policies, tests,
  render policy script, and README updates.
- [x] (2025-12-19 20:45Z) Updated Makefile targets, lint coverage, and roadmap
  entry for cert-manager.
- [x] (2025-12-19 21:09Z) Generated provider lock files, ran cert-manager
  tests/policy checks, and reran repo-wide gates (`make check-fmt`,

## Surprises & Discoveries

- Observation: `make test` exceeded the default 300s timeout on the first run;
  a second run completed once the Rust build cache was warm. Evidence:
  `/tmp/test.KwRxr1` ended during compilation; `/tmp/test.Bf2V4Z` succeeded.
- Observation: `make cert-manager-test` initially failed because OpenTofu
  formatting had not been applied to the new module. Evidence:
  `/tmp/cert-manager-test.yuPoxd` reported `tofu fmt -check` changes, resolved
  after `tofu fmt -recursive infra/modules/cert_manager`.
- Observation: Plan policy tests attempted to contact a stub Kubernetes API
  when no `KUBECONFIG` was supplied, and a Rego variable shadowed `data`.
  Evidence: `/tmp/cert-manager-test.SJaLvv` showed `dial tcp 127.0.0.1:443`
  errors; `issuers.rego` failed to compile until `data` was renamed.
- Observation: Conftest policies needed combined manifest input and staging
  warnings should not fail render checks. Evidence:
  `/tmp/cert-manager-test.2Ms11o` and the render policy script reported missing
  PDBs until `--combine` was used and warnings were allowed.

## Decision Log

- Decision: Use the Jetstack OCI chart repository
  (`oci://quay.io/jetstack/charts`) and pin cert-manager at `v1.19.2`.
  Rationale: Matches the declarative TLS guide and avoids unpinned updates.
  Date/Author: 2025-12-19 (assistant).
- Decision: Default to high-availability replica counts and render
  PodDisruptionBudgets when webhook or cainjector replicas exceed one.
  Rationale: Aligns with TLS availability guidance and supports safe
  disruptions. Date/Author: 2025-12-19 (assistant).
- Decision: Use token-based Vault authentication and require a CA bundle input,
  with an optional Secret for downstream consumption. Rationale: Keeps Vault
  integration explicit and consistent across modules. Date/Author: 2025-12-19
  (assistant).
- Decision: Keep the Namecheap webhook HelmRelease optional but enforce
  groupName/solverName alignment when present. Rationale: Supports external
  webhook deployments while preserving DNS-01 correctness. Date/Author:
  2025-12-19 (assistant).

## Outcomes & Retrospective

The cert-manager module, tests, policies, and design documentation are complete
and all required validation gates have passed. Apply-mode plan/policy checks
remain conditional on setting `CERT_MANAGER_KUBECONFIG_PATH` and the
Vault/Namecheap inputs so they can target a real cluster.

## Context and Orientation

The cert-manager module will live alongside the existing OpenTofu modules in
`infra/modules`. The `traefik` and `external_dns` modules show the expected
render/apply pattern, policy structure, and Terratest conventions. Key paths
and references:

- `infra/modules/traefik/` and `infra/modules/external_dns/` for module layout,
  `rendered_manifests` outputs, and OPA/Conftest policies.
- `infra/testutil/` for shared Terratest helpers (`TerraformEnvVars`,
  `SetupTerraform`).
- `scripts/traefik-render-policy.sh` and
  `scripts/external-dns-render-policy.sh` for render-policy automation.
- `docs/declarative-tls-guide.md` and
  `docs/cloud-native-ephemeral-previews.md` for expected cert-manager
  behaviours and GitOps layout. The TLS guide specifies the Jetstack OCI
  HelmRepository, chart version `v1.19.2`, high-availability values, and
  PodDisruptionBudgets for webhook and cainjector, plus a Namecheap DNS-01
  webhook solver whose `groupName` and `solverName` must match the
  `ClusterIssuer` configuration.
- `docs/opentofu-coding-standards.md` and
  `docs/opentofu-module-unit-testing-guide.md` for HCL rules and testing
  approach.
- `docs/ephemeral-previews-roadmap.md` for the roadmap entry that must be
  marked done when this module is complete.

Definitions used in this plan:

- **ACME**: Automated Certificate Management Environment (Let's Encrypt).
- **ClusterIssuer**: Cluster-scoped cert-manager issuer resource.
- **Render mode**: OpenTofu emits manifests for Flux to apply via GitOps.
- **Apply mode**: OpenTofu applies resources directly to a live cluster.
- **Vault issuer**: cert-manager issuer backed by HashiCorp Vault PKI.
- **CA bundle**: The certificate chain used to trust Vault's TLS endpoint.

## Plan of Work

First, decide and document the cert-manager module interface. Use
`docs/cert-manager-module-design.md` to record decisions such as the chart
version, ACME solver type (the TLS guide recommends a Namecheap DNS-01 webhook
solver with a private chart and aligned `groupName`), Vault auth mode (AppRole
vs token), and how the CA bundle is stored and referenced. Update
`docs/contents.md` to include the new design document, and ensure the choice
aligns with the TLS architecture in `docs/declarative-tls-guide.md`.

Next, scaffold `infra/modules/cert_manager` with the same structure as the
existing modules: `main.tf`, `variables-*.tf`, `outputs.tf`, `versions.tf`, a
`.tflint.hcl`, `README.md`, `examples/basic`, `examples/render`, `policy`, and
`tests`. Keep files under 400 lines by splitting logic (for example, separate
`issuers.tf` or `manifests.tf`). Ensure at least one module file starts with an
HCL module header comment using `//!` per repository conventions.

Implement the module so it supports both `render` and `apply` modes. Build
`locals` that normalize input values, map defaults, merge Helm values, and
construct manifests for HelmRepository, Namespace, HelmRelease, ClusterIssuers,
and an optional CA bundle Secret/ConfigMap. Include optional manifests for the
Namecheap webhook HelmRelease and the webhook/cainjector PodDisruptionBudgets
described in the TLS guide. Render mode must return a `rendered_manifests` map
keyed by the GitOps paths under `platform/cert-manager/` and
`platform/sources/`.

Follow the TLS guide for cert-manager release defaults: use a Jetstack
`HelmRepository` with `type: oci` and `url: oci://quay.io/jetstack/charts`, set
the cert-manager chart version to `v1.19.2`, enable CRD installation in
`spec.install`, and default to high-availability replica counts for the
controller, webhook, and cainjector. Render PodDisruptionBudgets when any of
those replica counts exceed one.

Define inputs with explicit `description`, `type`, and validation blocks. The
required inputs should include ACME email, ACME issuer names, and Vault
connection details (server URL, PKI path, auth secret reference, and CA bundle
material). Add inputs for the DNS-01 webhook solver configuration (group name,
solver name, and secret refs for the Namecheap API key and user), plus toggles
for webhook deployment and PodDisruptionBudgets. Optional inputs should allow
toggling staging/prod issuers, Vault issuer enablement, chart metadata, and
Helm values overrides. Follow `docs/opentofu-coding-standards.md` (nullable
handling, validations, snake case, and `tofu fmt`).

Expose outputs that downstream modules can consume: issuer names and refs for
ACME staging and production, issuer name/ref for Vault, secret references for
ACME account keys and Vault auth, and the CA bundle material (or its Secret
reference). Keep outputs consistent with `traefik` so the `nile-valley-infra-k8s`
action can wire values between modules.

Add examples mirroring existing modules. The apply-mode example must include
provider configuration and `kubeconfig_path` validation. The render example
should only depend on module inputs and export `rendered_manifests`. Duplicate
module defaults in the example variables so Terratest can override them.

Create OPA/Conftest policies for both rendered manifests and plan output.
Manifest policies should enforce pinned chart versions, correct sourceRef,
namespace consistency, PDB presence when replica counts exceed one, and
required issuer settings. Plan policies should inspect `kubernetes_manifest`
resources for ACME and Vault issuers, asserting HTTPS endpoints, required
email, solver configuration, Vault auth presence, and warnings for staging or
missing CA bundle data. Add plan policy checks that webhook `groupName` and
solver configuration are consistent when the webhook is enabled.

Implement Terratest coverage under `infra/modules/cert_manager/tests/` using
`infra/testutil`. Add happy-path tests for render output and output wiring,
plus unhappy-path tests for missing or invalid variables. Use table-driven
cases for validation errors, and include policy tests that validate both
accepted and rejected payloads. Include behavioural checks that run
`tofu plan -detailed-exitcode` to guard against destructive or drift changes.
Add an apply-mode Terratest scenario that runs `tofu apply` in a temporary
workspace when the required environment variables are present, ensuring a full
create/destroy cycle without polluting the working tree.

Update the Makefile to add `cert-manager-test` and `cert-manager-policy`
targets, include them in `INFRA_TEST_TARGETS`, and add `tflint` coverage under
`lint-infra`. Create a `scripts/cert-manager-render-policy.sh` helper modelled
on the existing render-policy scripts.

Finally, update `docs/ephemeral-previews-roadmap.md` to mark the cert-manager
module entry as done, and run all required format, lint, and test
commands with log capture. Document any design decisions in the design document
and update `docs/contents.md` accordingly.

## Concrete Steps

All commands should be run from
`/mnt/home/leynos/Projects/nile-valley.worktrees/infra-phase-2-cert-manager`. Use
a 300-second timeout and capture logs with `tee` for any command with long
output.

1. Create the module and policy scaffolding.

    mkdir -p infra/modules/cert_manager/{examples/basic,examples/render,policy/manifests,policy/plan,tests}

2. Draft the design document and update the documentation index.

    cat <<'DOC' > docs/cert-manager-module-design.md
    (Write the design decisions, interface details, and rationale here.)
    DOC

    (Update docs/contents.md to include the new design doc link.)

3. Implement module files and examples following the plan above. Keep module
   file sizes below 400 lines by splitting files as needed.

4. Generate provider lock files for the module and examples.

    timeout 300s bash -lc '
      tofu -chdir=infra/modules/cert_manager init -input=false -no-color
    '
    timeout 300s bash -lc '
      tofu -chdir=infra/modules/cert_manager/examples/basic \
        init -input=false -no-color
    '
    timeout 300s bash -lc '
      tofu -chdir=infra/modules/cert_manager/examples/render \
        init -input=false -no-color
    '

5. Add Terratest suites and initialize the Go module for tests.

    timeout 300s bash -lc '
      cd infra/modules/cert_manager/tests
      go mod init nile-valley/infra/modules/cert_manager/tests
    '
    timeout 300s bash -lc '
      cd infra/modules/cert_manager/tests
      go mod tidy
    '

6. Add OPA policies and the render-policy script.

    (Create scripts/cert-manager-render-policy.sh modelled on existing
    render-policy scripts.)

7. Update Makefile targets and infra lint list to include cert-manager.

8. Run infra checks and policy suites with log capture.

    timeout 300s bash -lc \
      'set -o pipefail; make check-test-deps 2>&1 | tee /tmp/nile-valley-check-test-deps.log'
    timeout 300s bash -lc \
      'set -o pipefail; make cert-manager-test 2>&1 | tee /tmp/nile-valley-cert-manager-test.log'
    timeout 300s bash -lc \
      'set -o pipefail; make cert-manager-policy 2>&1 | tee /tmp/nile-valley-cert-manager-policy.log'

9. Run the apply-mode behavioural test in an ephemeral workspace when
   credentials are available. Record the environment variables used in the
   design doc.

    timeout 300s bash -lc 'set -o pipefail; \
      CERT_MANAGER_KUBECONFIG_PATH=/path/to/kubeconfig \
      CERT_MANAGER_ACME_EMAIL=<platform@example.test> \
      CERT_MANAGER_NAMECHEAP_SECRET_NAME=namecheap-api-credentials \
      CERT_MANAGER_VAULT_SERVER=VAULT_URL \
      CERT_MANAGER_VAULT_PKI_PATH=pki/sign/example \
      CERT_MANAGER_VAULT_TOKEN_SECRET_NAME=vault-token \
      CERT_MANAGER_VAULT_CA_BUNDLE_PEM="$$(cat /path/to/vault-ca.pem)" \
      make cert-manager-test 2>&1 | tee /tmp/nile-valley-cert-manager-apply.log'

10. If any GitHub Actions files were touched, run the action lint suite and
   (where appropriate) add `act`-driven pytest integration tests following
   `docs/local-validation-of-github-actions-with-act-and-pytest.md`.

    timeout 300s bash -lc 'set -o pipefail; make lint-actions 2>&1 | tee /tmp/nile-valley-lint-actions.log'
    timeout 300s bash -lc 'set -o pipefail; uv run pytest \
      tests/test_workflow_integration.py 2>&1 | tee /tmp/nile-valley-act-tests.log'

11. Run documentation formatting and linting after doc changes.

    timeout 300s bash -lc 'set -o pipefail; make fmt 2>&1 | tee /tmp/nile-valley-fmt.log'
    timeout 300s bash -lc 'set -o pipefail; make markdownlint 2>&1 | tee /tmp/nile-valley-markdownlint.log'

12. Run the required repository-wide gates before completion.

    timeout 300s bash -lc 'set -o pipefail; make check-fmt 2>&1 | tee /tmp/nile-valley-check-fmt.log'
    timeout 300s bash -lc 'set -o pipefail; make lint 2>&1 | tee /tmp/nile-valley-lint.log'
    timeout 300s bash -lc 'set -o pipefail; make test 2>&1 | tee /tmp/nile-valley-test.log'

## Validation and Acceptance

The work is complete when all of the following are true:

- `infra/modules/cert_manager` exists with module files, README, examples,
  policies, and Terratest suites matching repository conventions.
- Render mode produces a non-empty `rendered_manifests` map containing
  `platform/cert-manager/helmrelease.yaml`, ACME issuer manifests, the Vault
  issuer manifest when enabled, and webhook/PDB manifests when enabled.
- Outputs include issuer names, issuer refs, secret references for ACME and
  Vault, and CA bundle material or CA bundle Secret reference.
- `make cert-manager-test` and `make cert-manager-policy` pass locally and
  cover both happy and unhappy paths (invalid inputs, missing values, invalid
  endpoints, provider/API failures, and policy rejections).
- `tofu plan -detailed-exitcode` is exercised in tests or Makefile targets and
  handles exit code 2 as a drift signal.
- A successful apply-mode test runs in a temporary workspace when credentials
  are supplied, and the test cleans up after itself.
- The design decisions are recorded in the design document and linked from
  `docs/contents.md`.
- The cert-manager module entry in `docs/ephemeral-previews-roadmap.md` is
  marked done.

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

- `platform/sources/cert-manager-repo.yaml`
- `platform/cert-manager/namespace.yaml`
- `platform/cert-manager/helmrelease.yaml`
- `platform/cert-manager/cluster-issuer-acme-staging.yaml`
- `platform/cert-manager/cluster-issuer-acme-production.yaml`
- `platform/cert-manager/cluster-issuer-vault.yaml`
- `platform/cert-manager/ca-bundle.yaml`
- `platform/cert-manager/namecheap-webhook-helmrelease.yaml`
- `platform/cert-manager/pdb-cert-manager-webhook.yaml`
- `platform/cert-manager/pdb-cert-manager-cainjector.yaml`
- `platform/cert-manager/kustomization.yaml`

## Interfaces and Dependencies

The module must declare the following providers in
`infra/modules/cert_manager/versions.tf`:

- `opentofu/kubernetes` ~> 2.25.0
- `opentofu/helm` ~> 2.13.0

Expected inputs (names can be refined but must be stable and documented):

- `mode` (`render` or `apply`).
- `namespace`, `create_namespace`, `flux_namespace`,
  `flux_helm_repository_name`.
- Chart metadata (`chart_repository`, `chart_name`, `chart_version`).
- ACME settings (`acme_email`, `acme_staging_server`, `acme_production_server`,
  `acme_staging_issuer_name`, `acme_production_issuer_name`, webhook solver
  settings, and secret refs).
- Vault settings (`vault_server`, `vault_pki_path`, `vault_auth_secret_name`,
  `vault_auth_secret_key`, and CA bundle material).
- Webhook settings (`webhook_enabled`, `webhook_group_name`,
  `webhook_solver_name`, `webhook_chart_repository`, `webhook_chart_version`,
  `namecheap_api_secret_name`, `namecheap_api_key_key`,
  `namecheap_api_user_key`).

Expected outputs:

- `acme_staging_issuer_name`, `acme_production_issuer_name` and their issuer
  ref objects.
- `vault_issuer_name` and its issuer ref.
- Secret references for ACME account keys and Vault auth.
- CA bundle material (or the Secret reference that carries it).
- `rendered_manifests` map for render mode.

## Revision note

- 2025-12-19: Recorded completed implementation steps (module, policies, tests,
  scripts, README, Makefile updates) and logged finalized decisions. Validation
  steps and lockfile generation remain outstanding and are called out in
  Progress.
- 2025-12-19: Updated the plan to reflect completed validation gates, added
  policy/test fixes for conftest and KUBECONFIG handling, and captured the
  observed validation hiccups.
- 2025-12-20: Updated chart version references to v1.19.2, expanded ACME on
  first use, and aligned wording/spelling with review feedback. No remaining
  work was added.
