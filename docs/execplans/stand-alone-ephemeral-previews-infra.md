# Remove Wildside-Specific Elements for Nile Valley

This ExecPlan is a living document. The sections `Constraints`, `Tolerances`,
`Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`, and
`Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: APPROVED

No `PLANS.md` file exists in this repository.

## Purpose / Big Picture

Transform this repository from a Wildside application monorepo into a
stand-alone Nile Valley infrastructure repo that can support multiple
applications that provide a suitable Helm chart. Success is visible when the
repo contains only platform and delivery infrastructure, documentation and
scripts reference Nile Valley rather than Wildside, and validation passes for
infrastructure tooling without depending on removed application code. A new
application should be able to adopt the platform by following the updated
Nile Valley documentation and supplying its own Helm chart from another repo
(e.g. `../ghillie`, `../wildside`).

## Constraints

- Keep the infrastructure automation functional and idempotent. The composite
  action that provisions clusters and renders GitOps manifests must still run
  end-to-end after renaming and generalisation.
- Retain a single example Helm chart, but remove all Wildside application
  code and assets outside that example.
- Maintain en-GB spelling in documentation and comments.
- Use the Makefile targets for formatting, linting, and tests. Run all quality
  gates before committing any changes.
- Follow the documentation style guide in `docs/documentation-style-guide.md`.
- Do not introduce new external dependencies without explicit review and
  documentation updates.
- Any repository-wide renames must preserve git history and be reflected in
  tests, scripts, and documentation.

## Tolerances (Exception Triggers)

- Scope: if removing Wildside elements requires edits across more than 200
  files or a net change above 8,000 lines, stop and escalate before
  proceeding.
- Interfaces: if a public action interface must change without a backwards
  compatibility story (name, inputs, outputs), stop and confirm the intended
  breaking strategy.
- Dependencies: if we need to add or replace a major toolchain (e.g. replace
  Makefile targets, add a new language runtime), stop and confirm.
- Validation: if `make lint`, `make check-fmt`, or `make test` fail after two
  focused attempts to fix issues, stop and escalate.
- Ambiguity: if there are multiple valid choices for what to delete vs.
  preserve (e.g. keeping a Wildside sample app), stop and ask for direction.

## Risks

- Risk: Removing application code may break Makefile targets and CI workflows.
  Severity: high
  Likelihood: medium
  Mitigation: update Makefile and workflows in the same commit as removals;
  adjust quality gates to align with the new infra-only scope.

- Risk: Renaming actions and modules may leave stale references in docs,
  scripts, or tests.
  Severity: high
  Likelihood: medium
  Mitigation: run an exhaustive search for `wildside` references, define an
  allowed list, and enforce via a final audit step.

- Risk: The platform docs are large and tightly coupled to Wildside examples.
  Severity: medium
  Likelihood: high
  Mitigation: plan a structured documentation rewrite with clear placeholders
  and a short "How to integrate a new app" section.

- Risk: External repositories or workflows may still depend on the old action
  names or paths.
  Severity: medium
  Likelihood: medium
  Mitigation: document the rename and provide a migration note in README and
  docs, plus a compatibility mapping table.

## Progress

- [x] (2026-01-30 00:00Z) Reviewed key infra roadmap and architecture docs.
- [x] (2026-01-30 00:00Z) Scanned repository for Wildside-specific references
  in infra, scripts, deploy assets, and docs.
- [x] (2026-01-30 00:00Z) Defined repo boundary: remove Wildside app code,
  retain an example Helm chart.
- [x] (2026-01-30 00:00Z) Confirmed naming convention: `nile-valley`.
- [ ] Produce a concrete Wildside removal and rename inventory list.
- [ ] Draft the implementation steps and validation plan.

## Surprises & Discoveries

- Observation: Wildside-specific references are pervasive in infra scripts,
  OpenTofu modules, GitHub Actions, and Helm charts, not only documentation.
  Evidence: `rg -n "wildside"` across infra, scripts, and deploy paths.
  Impact: The removal plan must include code and test updates, not just docs.

## Decision Log

- Decision: Use this ExecPlan to guide the removal of Wildside-specific
  elements before any implementation.
  Rationale: The change spans infra, scripts, docs, and CI; a controlled plan
  reduces risk.
  Date/Author: 2026-01-30 / Codex
- Decision: Remove Wildside application code but keep a single example Helm
  chart for integration guidance.
  Rationale: The repo is now infrastructure-focused, yet needs a concrete
  chart reference for adopters.
  Date/Author: 2026-01-30 / Codex
- Decision: Use `nile-valley` as the naming convention for actions, repos,
  and defaults.
  Rationale: Aligns with the new project identity and avoids Wildside naming.
  Date/Author: 2026-01-30 / Codex

## Outcomes & Retrospective

Pending execution.

## Context and Orientation

This repository currently mirrors the Wildside monorepo. It includes
application code (`backend/`, `frontend-pwa/`, `packages/`, `crates/`),
application deployment assets (`deploy/charts/wildside`, `deploy/k8s`), and
infrastructure automation (`infra/`, `scripts/`, `.github/actions/`). The
infrastructure for ephemeral previews is described in
`docs/cloud-native-ephemeral-previews.md` and
`docs/ephemeral-previews-roadmap.md`, but these documents are written from the
Wildside perspective and reference `wildside-infra`, `wildside-apps`, and the
`wildside-infra-k8s` action. The primary composite action lives in
`.github/actions/wildside-infra-k8s/action.yml`, while supporting Python
helpers sit in `scripts/` (e.g. `scripts/prepare_infra_k8s_inputs.py`) and the
OpenTofu modules and tests are in `infra/`.

The goal is to remove Wildside-specific elements so Nile Valley becomes a
stand-alone infrastructure platform usable by multiple applications, with
examples provided in sibling repos (e.g. `../ghillie`, `../wildside`).

## Plan of Work

Stage A: Define scope and inventory (no code changes).

- Produce a definitive inventory of Wildside-specific files and identifiers.
  Use a repo-wide search for `wildside`, `wildside-app`, `wildside-infra`,
  `wildside-apps`, and `wildside.cc`. Group findings into: application code,
  deployment assets, infra modules/tests, scripts/actions, and documentation.
- Decide whether to delete application code entirely or relocate it into an
  `examples/` directory. This decision affects tooling, Makefile targets, and
  CI workflows. Escalate if unclear.
- Decide on consistent naming for Nile Valley components (e.g.
  `nile-valley-infra-k8s` action, `nile-valley-infra` and `nile-valley-apps`
  repos) and document the mapping from old to new names.

Stage B: Repository pruning and structural updates.

- Remove Wildside application components so the repo contains only
  infrastructure-related code. This likely includes `backend/`,
  `frontend-pwa/`, `packages/`, `crates/`, `spec/`, and Kustomize overlays
  under `deploy/`, while retaining a single example Helm chart under a neutral
  name (e.g. `deploy/charts/example-app`).
- Update the Makefile, CI workflows, and dependency manifests to align with
  the reduced scope. Remove steps that build or test the deleted application
  code. Preserve infra test and lint targets.
- Update Go module paths under `infra/` to remove the `wildside/...` prefix and
  use a Nile Valley naming convention.

Stage C: Rename and generalise infrastructure automation.

- Rename `.github/actions/wildside-infra-k8s` to a Nile Valley name and update
  action metadata, inputs, outputs, and documentation references.
- Update all Python helper scripts under `scripts/` to remove Wildside naming
  in module docstrings, defaults, and help text. Adjust any default values that
  embed Wildside-specific bucket names, repo names, email addresses, or DNS
  domains so they become generic placeholders or required inputs.
- Update OpenTofu modules and defaults that embed Wildside names (e.g.
  `infra/modules/platform_render/variables.tf`, `infra/modules/cnpg/*`,
  `infra/backend-config/spaces.tfbackend`) with neutral or parameterised
  values.
- Update infra tests to match new naming and module paths. Ensure Go test
  imports and module replacements are aligned with the updated module paths.

Stage D: Documentation overhaul.

- Rewrite `README.md` to describe Nile Valley, its purpose, and how to use it
  with a third-party application Helm chart plus the bundled example chart.
- Update `docs/contents.md` to point to Nile Valley-oriented infrastructure
  docs and remove links that are purely about the Wildside application.
- Update `docs/cloud-native-ephemeral-previews.md` and
  `docs/ephemeral-previews-roadmap.md` to describe Nile Valley generically,
  replacing Wildside repo names and actions with Nile Valley equivalents.
- Remove or move Wildside-specific runbooks (e.g.
  `docs/runbooks/session-key-rotation.md`) that only apply to the application
  rather than the platform.
- Add a short "Integrating a new application" section that points to sibling
  repos (`../ghillie`, `../wildside`) as examples and lists required inputs
  (Helm chart location, secrets contract, image registry, domain naming).

Stage E: Validation and audit.

- Run formatting, linting, and tests via Makefile. Use `tee` to capture logs
  per the repo guidance.
- Perform a final audit search for `wildside` and document any remaining
  references that are intentionally retained (if any). Remove or fix all other
  occurrences.
- Update `docs/contents.md` and any new docs to ensure the documentation index
  remains accurate.

## Concrete Steps

1. Inventory Wildside references and categorise them.

   - Run:
     rg -n "wildside" . | tee \
       /tmp/inventory-nile-valley-$(git branch --show).out

   - Summarise the output into a short, categorised list in this ExecPlan
     (append under `Surprises & Discoveries` or a new sub-section).

2. Decide and document the repository boundary.

   - Confirm whether application code is deleted or moved to `examples/`.
   - Record the decision in `Decision Log`.

3. Remove or relocate app code and update tooling.

   - If deleting, remove directories and clean corresponding config files.
   - Update `Makefile`, `.github/workflows/ci.yml`, and dependency manifests
     to remove references to deleted areas.
   - Commit the change after `make lint`, `make check-fmt`, and `make test`
     pass.

4. Rename and generalise infra automation.

   - Rename `.github/actions/wildside-infra-k8s` directory and update action
     metadata to match new naming.
   - Update `scripts/` module docstrings, defaults, and tests to remove
     Wildside-specific values.
   - Update infra module defaults and test fixtures to remove Wildside naming.
   - Commit the change with all quality gates passing.

5. Update documentation and index.

   - Rewrite README and infra docs to be Nile Valley-specific.
   - Update `docs/contents.md` with the new structure.
   - Run documentation linting: `make markdownlint` and `make nixie`.
   - Commit documentation changes after formatting and linting succeed.

6. Final audit and verification.

   - Re-run `rg -n "wildside" .` and confirm only intentional references
     remain. If none should remain, ensure the report is empty.
   - Run `make lint`, `make check-fmt`, and `make test` one last time.

## Validation and Acceptance

Success criteria:

- The repo focuses on Nile Valley infra; Wildside application assets are removed
  or relocated according to the agreed boundary decision.
- No Wildside-specific naming remains in infra automation, defaults, or docs
  (unless explicitly retained for historical context and documented).
- `make lint`, `make check-fmt`, `make test`, `make markdownlint`, and
  `make nixie` all pass using the updated scope.
- A new application can follow the documentation to integrate its Helm chart
  without referencing Wildside artefacts.

## Idempotence and Recovery

- Removal steps are repeatable: re-running deletes should be safe because they
  target known directories.
- If a validation step fails, fix issues and re-run the same Makefile targets
  until they pass or a tolerance triggers escalation.
- Keep commits small and scoped so rollback is straightforward via `git revert`
  if needed.

## Artifacts and Notes

Record key command outputs (inventory search, lint/test runs) in `/tmp` logs
using `tee`. Reference these logs in commit messages or the ExecPlan as
appropriate.

## Interfaces and Dependencies

- Composite action (rename required):
  - Current: `.github/actions/wildside-infra-k8s/action.yml`
  - Proposed: `.github/actions/nile-valley-infra-k8s/action.yml` (or another
    agreed name).
  - Inputs/outputs must remain functionally equivalent, with any Wildside
    defaults replaced by neutral placeholders.
- Python helper scripts under `scripts/` are treated as internal interfaces for
  the composite action. Function signatures should remain stable, but names and
  defaults may be updated to match the new domain.
- Go test modules under `infra/**/tests` must align with the new module path
  and helper package names.

## Revision note

Updated status to APPROVED, captured the repo boundary decision (remove
Wildside app code, retain an example Helm chart), and recorded the
`nile-valley` naming convention. Adjusted scope language in Stage B and
documentation goals accordingly.
