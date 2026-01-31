# Document OpenTofu module interoperability contract

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

<!-- ═══════════════════ WHAT (Acceptance Criteria) ═══════════════════ -->

## Purpose / big picture

The `nile-valley-infra-k8s` action needs to thread outputs from one OpenTofu
module into another's inputs. For example, it passes DNS zone identifiers from
the `external_dns` module to Traefik, certificate issuer references from
`cert_manager` to data services, and secret store references from `vault_eso`
to workloads consuming credentials.

After this work:

- Platform engineers can consult a central interoperability contract document
  explaining how modules interconnect.
- Each module's README documents its inputs, outputs, and `sync_policy_contract`
  (where applicable).
- Documentation accuracy tests verify README contents match actual HCL code.
- The `cnpg` and `valkey` modules have READMEs following the established
  pattern.

## Validation and acceptance

1. **CNPG README exists** at `infra/modules/cnpg/README.md`:
   - Run `test -f infra/modules/cnpg/README.md && echo OK` → `OK`
   - Includes Inputs table, Outputs table, Sync Policy Contract section

2. **Valkey README exists** at `infra/modules/valkey/README.md`:
   - Run `test -f infra/modules/valkey/README.md && echo OK` → `OK`
   - Includes Inputs table, Outputs table, Sync Policy Contract section

3. **Interoperability contract document exists** at
   `docs/opentofu-module-interoperability-contract.md`:
   - Contains module dependency diagram (Mermaid)
   - Documents the `sync_policy_contract` pattern
   - Documents issuer reference threading
   - Documents DNS zone mapping

4. **Documentation accuracy tests pass**:
   - `make cnpg-test` passes (includes README accuracy checks)
   - `make valkey-test` passes (includes README accuracy checks)

5. **All quality gates pass**:
   - `make check-fmt` exits 0
   - `make lint` exits 0
   - `make markdownlint` exits 0
   - `make test` exits 0

6. **Roadmap updated**: Line 83 of `docs/ephemeral-previews-roadmap.md` shows
   `[x]` instead of `[ ]`.

<!-- ═══════════════════ HOW (Implementation Approach) ═══════════════════ -->

## Context and orientation

The repository contains nine OpenTofu modules under `infra/modules/`:

| Module            | Purpose                          | Has README |
| ----------------- | -------------------------------- | ---------- |
| `doks`            | DigitalOcean Kubernetes cluster  | Yes        |
| `fluxcd`          | FluxCD GitOps controller         | Yes        |
| `traefik`         | Ingress controller + ACME issuer | Yes        |
| `external_dns`    | DNS automation (Cloudflare)      | Yes        |
| `cert_manager`    | Certificate management           | Yes        |
| `vault_appliance` | Vault droplet infrastructure     | Yes        |
| `vault_eso`       | External Secrets Operator (ESO)  | Yes        |
| `cnpg`            | CloudNativePG (PostgreSQL)       | **No**     |
| `valkey`          | Valkey/Redis cluster             | **No**     |

All modules support dual operational modes:

- **`mode = "render"`** (default): Outputs `rendered_manifests` map for GitOps
- **`mode = "apply"`**: Applies resources directly via Kubernetes/Helm providers

Three modules expose a `sync_policy_contract` output for downstream
consumption: `vault_eso`, `cnpg`, and `valkey`. This structured object provides
all information workloads need to consume the service.

## Plan of work

1. **Create CNPG README** following the `vault_eso/README.md` pattern:
   - Overview, Prerequisites, Usage (render/apply), Inputs table, Outputs table
   - Sync Policy Contract section with example structure
   - Integration examples showing ESO credential management

2. **Create Valkey README** following the same pattern:
   - Include TLS integration with cert-manager
   - Document the `sync_policy_contract` output

3. **Create documentation accuracy tests** for both modules:
   - Verify all outputs documented in README exist in `outputs.tf`
   - Verify all required inputs documented in README exist in `variables-*.tf`

4. **Create central interoperability contract document**:
   - Module dependency diagram (Mermaid)
   - Explanation of render vs apply modes
   - Interoperability patterns (sync_policy_contract, issuer refs, DNS zones)
   - Module output threading examples
   - Reference summary table

5. **Update documentation index** (`docs/contents.md`)

6. **Mark roadmap task complete**

## Concrete steps

All commands run from repository root.

### Step 1: Create CNPG README

    # Create infra/modules/cnpg/README.md with:
    # - Overview of CloudNativePG module
    # - Prerequisites section
    # - Render mode and Apply mode usage examples
    # - Inputs table (from variables-core.tf, variables-cluster.tf,
    #   variables-backup.tf, variables-credentials.tf)
    # - Outputs table (from outputs.tf)
    # - Sync Policy Contract section with structure example
    # - Integration with vault_eso module
    # - Resources created section

### Step 2: Create Valkey README

    # Create infra/modules/valkey/README.md with:
    # - Overview of Valkey (Redis-compatible) module
    # - Prerequisites section
    # - Render mode and Apply mode usage examples
    # - Inputs table (from variables-core.tf, variables-cluster.tf,
    #   variables-credentials.tf, variables-tls.tf)
    # - Outputs table (from outputs.tf)
    # - Sync Policy Contract section with structure example
    # - TLS integration with cert-manager
    # - ESO integration for credentials
    # - Resources created section

### Step 3: Create documentation accuracy tests

    # Add to infra/modules/cnpg/tests/readme_accuracy_test.go:
    # - Parse README.md for documented outputs
    # - Parse outputs.tf for actual outputs
    # - Verify all outputs match
    # - Same pattern for valkey

### Step 4: Create interoperability contract document

    # Create docs/opentofu-module-interoperability-contract.md with:
    # - Module dependency graph (Mermaid)
    # - Render vs Apply mode explanation
    # - sync_policy_contract pattern documentation
    # - Issuer reference threading (cert_manager → data services)
    # - DNS zone mapping (external_dns → traefik)
    # - Secret store references (vault_eso → workloads)
    # - Module reference summary table

### Step 5: Update docs/contents.md

    # Add entry under "Infrastructure and delivery":
    # - [OpenTofu module interoperability contract]
    #     (opentofu-module-interoperability-contract.md)

### Step 6: Validate

    make check-fmt
    make lint
    make markdownlint

### Step 7: Run tests

    make cnpg-test
    make valkey-test
    make test

### Step 8: Update roadmap

    # Edit docs/ephemeral-previews-roadmap.md line 83:
    # Change "- [ ] **Module interoperability contract**"
    # to     "- [x] **Module interoperability contract**"

### Step 9: Commit

    git add -A
    git commit -m "Document module interoperability contract

    Add missing READMEs for cnpg and valkey modules following the established
    pattern from vault_eso. Create central interoperability contract document
    explaining how the nile-valley-infra-k8s action threads DNS zones, certificate
    issuers, and credential handles between modules.

    Include documentation accuracy tests that verify README contents match the
    actual HCL code.

    🤖 Generated with Claude Code (https://claude.com/claude-code)

    Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

## Interfaces and dependencies

### Key output structures

**vault_eso sync_policy_contract** (lines 47–59 of
`infra/modules/vault_eso/outputs.tf`):

    {
      kv_secret_store = {
        name       = "vault-kv"
        kind       = "ClusterSecretStore"
        mount_path = "secret"
      }
      vault_address         = "https://vault.example.com"
      auth_secret_name      = "vault-approle-credentials"
      auth_secret_namespace = "external-secrets"
    }

**cnpg sync_policy_contract** (lines 66–104 of `infra/modules/cnpg/outputs.tf`):

    {
      cluster = { name = "…", namespace = "…" }
      endpoints = {
        primary = { host = "…", port = 5432 }
        replica = { host = "…", port = 5432 }
      }
      database = { name = "…", owner = "…" }
      credentials = {
        superuser_secret = { name = "…", namespace = "…" }
        app_secret       = { name = "…", namespace = "…" }
      }
      backup          = { enabled = true, destination_path = "…", schedule = "…" }
      postgis_enabled = true
    }

**valkey sync_policy_contract** (lines 61–97 of
`infra/modules/valkey/outputs.tf`):

    {
      cluster   = { name = "…", namespace = "…" }
      endpoints = {
        primary = { host = "…", port = 6379 }
        replica = { host = "…", port = 6379 }
      }
      credentials = { secret_name = "…", secret_key = "…", namespace = "…" }
      tls         = { enabled = true, cert_issuer = "…" }
      persistence = { enabled = true, storage_class = "…", size = "…" }
      replication = { nodes = 1, replicas = 0 }
    }

### Certificate issuer references

**cert_manager** outputs `acme_staging_issuer_ref`,
`acme_production_issuer_ref`, and `vault_issuer_ref` in the format:

    { name = "letsencrypt-prod", kind = "ClusterIssuer", group = "cert-manager.io" }

**traefik** outputs `cluster_issuer_ref` in the same format.

### DNS zone mapping

**external_dns** outputs `managed_zones`:

    { "example.com" = "zone_id_abc123", "example.org" = "zone_id_def456" }

## Idempotence and recovery

All steps are idempotent:

- Creating files: Overwrites existing content
- Running tests: Safe to re-run
- Updating roadmap: Idempotent checkbox toggle

If tests fail, fix the documentation to match the code (or vice versa), then
re-run validation.

<!-- ═══════════════════ TRACKING (Living Sections) ═══════════════════ -->

## Progress

- [x] (2025-12-30) Create CNPG README (`infra/modules/cnpg/README.md`)
- [x] (2025-12-30) Create Valkey README (`infra/modules/valkey/README.md`)
- [x] (2025-12-30) Create documentation accuracy tests
- [x] (2025-12-30) Create interoperability contract document
- [x] (2025-12-30) Update `docs/contents.md`
- [x] (2025-12-30) Run validation (`make check-fmt`, `make lint`,
      `make markdownlint`)
- [x] (2025-12-30) Run tests (`make cnpg-test`, `make valkey-test`, `make test`)
- [x] (2025-12-30) Update roadmap (mark task complete)
- [x] (2025-12-30) Commit changes

## Surprises & discoveries

- **Observation**: ExecPlan markdown lint (MD046) failed when using fenced code
  blocks. The execplans skill requires indented code blocks (4 spaces) rather
  than triple-backtick fencing. **Resolution**: Converted all fenced blocks to
  indented blocks.

- **Observation**: Initial README accuracy tests used incorrect path
  (`filepath.Join("..", "..")`) for the module directory. Tests run from the
  `tests/` subdirectory, so the correct path is `".."`. **Resolution**: Fixed
  all path references in both test files.

## Decision log

- **Decision**: Follow `vault_eso/README.md` as the primary pattern for new
  READMEs rather than `cert_manager/README.md`. **Rationale**: `vault_eso`
  demonstrates the `sync_policy_contract` pattern, which is the key
  interoperability mechanism for data services. **Date/Author**: 2025-12-29

- **Decision**: Create documentation accuracy tests in Go using the existing
  Terratest infrastructure rather than shell scripts. **Rationale**: Consistent
  with existing test patterns; enables structured parsing and better error
  messages. **Date/Author**: 2025-12-29

## Outcomes & retrospective

All acceptance criteria met:

1. **CNPG README**: Created at `infra/modules/cnpg/README.md` with inputs table,
   outputs table, and sync policy contract section.

2. **Valkey README**: Created at `infra/modules/valkey/README.md` with inputs
   table, outputs table, sync policy contract section, TLS integration, and ESO
   integration documentation.

3. **Interoperability contract document**: Created at
   `docs/opentofu-module-interoperability-contract.md` with module dependency
   graph, render/apply mode explanation, and four interoperability patterns.

4. **Documentation accuracy tests**: Added Go-based tests that verify README
   contents match actual HCL code. All tests pass.

5. **Quality gates**: `make check-fmt`, `make lint`, `make markdownlint`, and
   `make test` all pass.

6. **Roadmap updated**: Line 83 of `docs/ephemeral-previews-roadmap.md` now
   shows `[x]`.

## Artifacts and notes

### Source files for CNPG inputs

- `infra/modules/cnpg/variables-core.tf` (15 variables)
- `infra/modules/cnpg/variables-cluster.tf` (17 variables)
- `infra/modules/cnpg/variables-backup.tf` (10 variables)
- `infra/modules/cnpg/variables-credentials.tf` (8 variables)

### Source files for Valkey inputs

- `infra/modules/valkey/variables-core.tf` (14 variables)
- `infra/modules/valkey/variables-cluster.tf` (18 variables)
- `infra/modules/valkey/variables-credentials.tf` (9 variables)
- `infra/modules/valkey/variables-tls.tf` (5 variables)

### Related documentation

- `docs/valkey-module-design.md` - Valkey design decisions
- `docs/execplans/infra-phase-2-cloud-native-pg-module.md` - CNPG design
- `docs/ephemeral-previews-roadmap.md` - Roadmap (task at line 83–85)
