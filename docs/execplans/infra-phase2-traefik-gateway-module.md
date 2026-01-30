# Phase 2.3: Traefik gateway module (CRDs + HelmRelease + annotations)

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

No `PLANS.md` exists in the repository root at the time this plan was written.

## Purpose / Big Picture

The Phase 2.3 roadmap item requires the Traefik gateway module to support a
GitOps (Git-based operations) workflow: render Flux-ready manifests (including
Traefik custom resource definitions (CRDs) and a `HelmRelease` values block)
rather than only applying directly via OpenTofu’s Helm/Kubernetes providers.

After completion, a newcomer can:

1. Render the Traefik platform manifests (CRDs + `HelmRelease` + Kustomize
   entrypoints) from `infra/modules/traefik` without needing a kubeconfig.
2. Configure cloud/provider-specific service annotations (DigitalOcean,
   AWS, etc.) through a typed module input and observe them in the rendered
   `HelmRelease` values.
3. Consume module outputs for:
   - dashboard hostname(s),
   - the default certificate issuer name to be used cluster-wide.
4. Validate changes locally using the repository gates:

This work must also:

- Include OpenTofu static checks (`tofu fmt -check`, `tofu validate`, `tflint`).
- Add/extend Terratest unit-style tests and Conftest policy tests.
- Add an optional end-to-end apply run (ephemeral workspace) that is gated
  behind explicit environment variables and uses `tofu plan -detailed-exitcode`
  to detect drift.
- Validate GitHub Actions with `yamllint` and `actionlint`.
- Record all design decisions in the relevant design documentation.

## Progress

- [x] (2025-12-15) Confirm current module gaps vs roadmap item.
- [x] (2025-12-15) Record design decisions and module contract in docs.
- [x] (2025-12-15) Implement render mode outputs (HelmRelease + CRDs +
      kustomization).
- [x] (2025-12-15) Add service annotations input and output contract updates.
- [x] (2025-12-15) Extend Terratest coverage (happy/unhappy paths).
- [x] (2025-12-15) Extend Conftest policies for rendered manifests.
- [x] (2025-12-15) Add `actionlint` validation to `make lint-actions`.
- [x] (2025-12-15) Run all quality gates and update the roadmap checkbox.
- [x] (2025-12-15) Commit and push to a new branch.

## Surprises & Discoveries

- Observation: `make lint-actions` currently validates composite actions using
  `yamllint` and `action-validator` but does not run `actionlint` against
  workflows. Evidence: `Makefile` target `lint-actions` lacks `actionlint`
  usage.

- Observation: The existing Traefik module is apply-to-cluster oriented
  (`helm_release` + `kubernetes_manifest`) and does not render Flux
  `HelmRelease` YAML nor vendor Traefik CRDs. Evidence:
  `infra/modules/traefik/main.tf` has no manifest rendering outputs.

- Observation: The initial vendored CRDs file accidentally contained terminal
  control characters, which caused YAML parsing failures in Conftest. Evidence:
  Conftest reported `yaml: control characters are not allowed` when testing
  rendered CRDs.

- Observation: The previous `lint-actions` implementation attempted to store
  null-delimited `find -print0` output inside a shell variable, which drops
  null bytes and concatenates paths. Evidence: `make lint` attempted to lint a
  non-existent path like
  `.github/workflows/ci.yml.github/workflows/delayed-pr-comment.yml`.

- Observation: GitHub composite action inputs do not support a `secret` key,
  but unit tests expected it. Evidence: `action-validator` rejected
  `.github/actions/bootstrap-vault-appliance/action.yml` until `secret: true`
  was removed and the test suite updated.

- Observation: Terratest’s `CopyTerraformFolderToTemp` did not remove its
  temporary directories, eventually filling `/tmp` and breaking `tofu init`
  with `no space left on device`. Evidence: `/tmp` reached 100% usage and
  provider installs failed until temporary directories were cleaned up.

## Decision Log

- Decision: Add an explicit module `mode` with two values:
  - `render` (default): generate YAML outputs only; no provider access required.
  - `apply`: perform cluster changes via Helm/Kubernetes providers.
  Rationale: The roadmap item is GitOps-oriented, but retaining the option to
  do a real apply in an explicitly gated, end-to-end validation step remains
  valuable. Date/Author: 2025-12-15 / Codex.

- Decision: Vendor Traefik CRDs into `infra/modules/traefik/crds/` pinned to
  the module’s chart version. Rationale: Deterministic, reviewable inputs;
  avoids network lookups at runtime and keeps “render” mode offline-friendly.
  Date/Author: 2025-12-15 / Codex.

- Decision: Keep existing outputs for backwards compatibility, but add new
  explicit output names for GitOps consumers:
  - `dashboard_hostnames` (list)
  - `default_certificate_issuer_name` (string)
  Rationale: The roadmap item asks for hostnames (plural) and explicitly names
  the “default certificate issuer”. Date/Author: 2025-12-15 / Codex.

- Decision: Extend action linting to include `actionlint` (in addition to
  `action-validator`). Rationale: Requirement from the task statement;
  `actionlint` validates workflow YAML semantics beyond schema validation.
  Date/Author: 2025-12-15 / Codex.

- Decision: Use explicit Rego package names and run Conftest with an explicit
  namespace. Rationale: Aligns with the existing FluxCD policy conventions and
  ensures scripts/tests always evaluate the intended policy rules. Date/Author:
  2025-12-15 / Codex.

## Outcomes & Retrospective

Completed outcomes:

- `infra/modules/traefik` renders Flux manifests including CRDs and a Traefik
  `HelmRelease` with correct values and service annotations.
- `dashboard_hostnames` and `default_certificate_issuer_name` are available for
  downstream modules/actions.
- Terratest covers render outputs and key unhappy paths.
- Conftest policies validate rendered manifests and enforce version pinning.
- `docs/ephemeral-previews-roadmap.md` marks the Traefik gateway module item as
  complete.

## Context and Orientation

Key files and directories:

- `docs/ephemeral-previews-roadmap.md`:
  Contains the unchecked Traefik gateway module roadmap item.

- `docs/cloud-native-ephemeral-previews.md`:
  Describes the GitOps contract and includes an example
  `platform/traefik/helmrelease.yaml` that the module should be able to
  reproduce.

- `infra/modules/traefik/`:
  The module under work. Today it installs Traefik using OpenTofu’s
  Helm/Kubernetes providers and creates a cert-manager `ClusterIssuer`.

- `infra/modules/traefik/tests/traefik_test.go`:
  Existing Terratest suite, already covering input validation and plan-based
  Conftest policy tests.

- `infra/modules/traefik/policy/`:
  Existing OPA policy (currently focused on `ClusterIssuer` plan JSON).

- `Makefile`:
  Provides `traefik-test`, `traefik-policy`, and global gates.

Terminology:

- “Flux HelmRelease”: Kubernetes CRD `HelmRelease` (`helm.toolkit.fluxcd.io/v2`)
  reconciled by Flux’s `helm-controller`.
- “Traefik CRDs”: Kubernetes `CustomResourceDefinition` objects defining
  `traefik.io/v1alpha1` resources such as `IngressRoute`.
- “Render mode”: producing YAML manifest outputs to commit into
  `nile-valley-infra` for Flux to reconcile.
- “Apply mode”: applying resources directly to a cluster via providers.

## Plan of Work

1. Update the Traefik OpenTofu module to support a render-only mode:
   - Add `mode` variable and gate provider-backed resources so render-only runs
     do not require kubeconfig or cluster access.
   - Add `rendered_manifests` output (map of target path -> YAML content).

2. Vendor Traefik CRDs and include them in rendered outputs.

3. Add a typed `service_annotations` variable and ensure it is emitted into
   the rendered `HelmRelease` values at `values.service.annotations`.

4. Extend outputs:
   - Add `dashboard_hostnames` output (empty unless enabled).
   - Add `default_certificate_issuer_name` output.

5. Expand automated testing:
   - Terratest: assert rendered YAML contains expected keys and values.
   - Conftest: add policies for rendered manifests (separate from plan
     policies).
   - Optional: gated apply workflow that uses an ephemeral workspace and
     validates drift with `tofu plan -detailed-exitcode`.

6. Tooling:
   - Add `actionlint` to `make lint-actions` and run it over workflows.
   - Keep `yamllint` validation.

7. Documentation:
   - Update `docs/cloud-native-ephemeral-previews.md` (or a dedicated design
     doc) to reflect the concrete module contract (rendered file set, output
     contract, ownership boundaries).
   - Mark the roadmap item complete.

## Concrete Steps

All commands run from the repo root:

    cd /mnt/home/leynos/Projects/nile-valley.worktrees/validate-traefik

Use this pattern for long commands to preserve output and exit status:

    set -o pipefail
    timeout 300s make <target> 2>&1 | tee "/tmp/nile-valley-<target>.log"
    status=${PIPESTATUS[0]}
    test "$status" -eq 0

Baseline checks:

    timeout 300s make -n traefik-test
    timeout 300s make -n traefik-policy
    timeout 300s make -n lint-actions

After implementation, run:

    set -o pipefail
    timeout 300s make check-fmt 2>&1 | tee /tmp/nile-valley-check-fmt.log
    test ${PIPESTATUS[0]} -eq 0

    set -o pipefail
    test ${PIPESTATUS[0]} -eq 0

    set -o pipefail
    timeout 300s make lint 2>&1 | tee /tmp/nile-valley-lint.log
    test ${PIPESTATUS[0]} -eq 0

    set -o pipefail
    timeout 300s make test 2>&1 | tee /tmp/nile-valley-test.log
    test ${PIPESTATUS[0]} -eq 0

## Validation and Acceptance

Acceptance requires:

1. Rendered outputs exist and are correct:
   - Terratest asserts `rendered_manifests` contains:
     - `platform/traefik/helmrelease.yaml`,
     - `platform/traefik/kustomization.yaml`,
     - at least one CRD YAML under `platform/traefik/crds/`.
   - Rendered `HelmRelease` YAML contains:
     - pinned chart version,
     - `values.service.annotations` reflecting module input.

2. Output contract:
   - `dashboard_hostnames` is empty unless dashboard is enabled.
   - `default_certificate_issuer_name` is present and documented.

3. Policy coverage:
   - Conftest denies at least one unsafe manifest configuration (unhappy path),
     and the deny is validated by an automated test.

4. Repository gates:
   - `make check-fmt`, `make lint`, and `make test` succeed.

5. GitHub Actions lint:
   - `make lint-actions` runs `yamllint` and `actionlint` successfully.

6. Documentation:
   - The design contract is recorded.
   - `docs/ephemeral-previews-roadmap.md` marks the Traefik gateway module item
     complete.

## Idempotence and Recovery

- Render mode must be deterministic and safe to re-run.
- Apply mode must be explicitly gated (no accidental applies). Any apply should:
  - create and use an ephemeral OpenTofu workspace,
  - run a post-apply `tofu plan -detailed-exitcode` and expect exit code 0,
  - destroy resources and delete the workspace on exit.

If a command fails, inspect the log:

    less /tmp/nile-valley-<target>.log

Then rerun only the failing target after fixing the underlying issue.

## Interfaces and Dependencies

At the end of the work, `infra/modules/traefik` exposes:

- Variables:
  - `mode` (`render` | `apply`), default `render`.
  - `service_annotations` (`map(string)`), default `{}`.

- Outputs:
  - `rendered_manifests` (`map(string)`): target GitOps path -> YAML string.
  - `dashboard_hostnames` (`list(string)`).
  - `default_certificate_issuer_name` (`string`).

Tooling dependencies:

- `tofu`, `tflint`, `conftest`
- `yamllint`, `actionlint`, `action-validator`
- Go toolchain for Terratest

## Revision note (required when editing an ExecPlan)

Initial version (2025-12-15): created based on current repo state and the
roadmap requirements for Phase 2.3 Traefik gateway module.

Revision (2025-12-15): Updated `Progress`, `Surprises & Discoveries`, and
`Outcomes & Retrospective` to reflect the completed implementation, including
lint/test gate fixes (action schema validation, Conftest policy package
selection, and Terratest temp directory cleanup).

Revision (2025-12-15): Added explicit Makefile pre-checks for
`TRAEFIK_ACME_EMAIL` and `TRAEFIK_CLOUDFLARE_SECRET_NAME` when
`TRAEFIK_KUBECONFIG_PATH` is set, so apply-mode validation fails fast with a
clear message.
