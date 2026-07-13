# ExternalDNS OpenTofu Module Implementation Plan

This plan implements the ExternalDNS module for Phase 2.3 of the ephemeral
previews infrastructure roadmap.

## Overview

Deliver a reusable OpenTofu module under `infra/modules/external_dns/` that:

- Supports multi-zone providers (Cloudflare)
- Accepts DNS zone mappings as input variables
- Emits managed zone IDs for downstream consumers
- Provides dual modes: `apply` (direct cluster) and `render` (GitOps manifests)
- Follows established patterns from the Traefik gateway module

## Implementation Status

| Requirement                               | Status       | Details                                                   |
| ----------------------------------------- | ------------ | --------------------------------------------------------- |
| Multi-zone providers                      | ✅ Complete  | Cloudflare with multiple zones via `domain_filters`       |
| Accept DNS zone mappings                  | ✅ Complete  | `zone_id_filter` variable maps domains to zone IDs        |
| Emit managed zone IDs                     | ✅ Complete  | `zone_id_filter` and `managed_zones` outputs              |
| Dual modes                                | ✅ Complete  | `apply` and `render` modes implemented                    |
| Terratest coverage                        | ✅ Complete  | Zone ID validation, output, and Helm values tests         |
| Open Policy Agent (OPA)/Conftest policies | ✅ Complete  | Plan policy warns on zone-id-filter without domainFilters |

## File Structure

```text
infra/modules/external_dns/
├── main.tf                      # Core logic, locals, resources, rendered manifests
├── variables.tf                 # Input variables with validations
├── outputs.tf                   # Module outputs including rendered_manifests
├── versions.tf                  # OpenTofu and provider version constraints
├── README.md                    # Module documentation
├── .tflint.hcl                  # TFLint configuration
├── policy/
│   ├── manifests/
│   │   └── helmrelease.rego     # Open Policy Agent (OPA) policy for rendered HelmRelease validation
│   └── plan/
│       └── externaldns.rego     # OPA policy for plan-time validation
├── examples/
│   ├── basic/
│   │   ├── main.tf              # Apply-mode example with kubeconfig
│   │   ├── variables.tf         # Example variables
│   │   └── outputs.tf           # Example outputs
│   └── render/
│       ├── main.tf              # Render-mode example (no cluster)
│       ├── variables.tf         # Example variables
│       └── outputs.tf           # Example outputs
└── tests/
    ├── external_dns_test.go     # Terratest integration tests
    ├── go.mod
    └── go.sum
```

## Implementation Steps

### Step 1: Create Module Core Files

#### 1.1 `versions.tf`

- OpenTofu requirement: `>= 1.6.0, < 2.0.0`
- Providers: `opentofu/kubernetes ~> 2.25.0`, `opentofu/helm ~> 2.13.0`
- Follow pattern from `infra/modules/traefik/versions.tf`

#### 1.2 `variables.tf`

Required inputs:

| Variable                           | Type           | Description                                           |
| ---------------------------------- | -------------- | ----------------------------------------------------- |
| `mode`                             | `string`       | `"render"` or `"apply"`                               |
| `namespace`                        | `string`       | Namespace for ExternalDNS (default: `"external-dns"`) |
| `domain_filters`                   | `list(string)` | DNS domains to manage (e.g., `["example.com"]`)       |
| `cloudflare_api_token_secret_name` | `string`       | Kubernetes secret with Cloudflare API token           |
| `txt_owner_id`                     | `string`       | Unique identifier for ownership TXT records           |

Optional inputs:

| Variable                          | Type           | Default                                             | Description                                       |
| --------------------------------- | -------------- | --------------------------------------------------- | ------------------------------------------------- |
| `create_namespace`                | `bool`         | `true`                                              | Create the namespace                              |
| `chart_repository`                | `string`       | `"https://kubernetes-sigs.github.io/external-dns/"` | Helm repo URL                                     |
| `chart_name`                      | `string`       | `"external-dns"`                                    | Helm chart name                                   |
| `chart_version`                   | `string`       | `"1.16.1"`                                          | Helm chart version                                |
| `helm_release_name`               | `string`       | `"external-dns"`                                    | Helm release name                                 |
| `helm_timeout`                    | `number`       | `600`                                               | Helm timeout seconds                              |
| `helm_wait`                       | `bool`         | `true`                                              | Wait for Helm success                             |
| `helm_values`                     | `list(string)` | `[]`                                                | Inline YAML values                                |
| `helm_values_files`               | `list(string)` | `[]`                                                | Value file paths                                  |
| `policy`                          | `string`       | `"sync"`                                            | DNS policy (`sync` or `upsert-only`)              |
| `cloudflare_proxied`              | `bool`         | `false`                                             | Enable Cloudflare proxy by default                |
| `cloudflare_api_token_secret_key` | `string`       | `"token"`                                           | Key in the secret                                 |
| `dns_records_per_page`            | `number`       | `5000`                                              | API pagination size                               |
| `log_level`                       | `string`       | `"info"`                                            | Log level                                         |
| `sources`                         | `list(string)` | `["ingress", "service"]`                            | Kubernetes resource sources                       |
| `crd_enabled`                     | `bool`         | `true`                                              | Enable DNSEndpoint CustomResourceDefinition (CRD) |
| `flux_namespace`                  | `string`       | `"flux-system"`                                     | Flux namespace (render mode)                      |
| `flux_helm_repository_name`       | `string`       | `"external-dns"`                                    | Flux HelmRepository name                          |
| `service_monitor_enabled`         | `bool`         | `false`                                             | Create ServiceMonitor                             |

All inputs must include:

- `description`
- `type`
- `nullable = false` (for required inputs)
- `validation` blocks with precise error messages

#### 1.3 `main.tf`

Structure:

1. **Locals block**: Normalize inputs with `trimspace()`, construct Helm values
2. **Mode flags**: `local.is_apply_mode`, `local.is_render_mode`
3. **Common labels**: `app.kubernetes.io/managed-by = "opentofu"`
4. **Default Helm values map**: Provider config, domain filters, policy, sources
5. **Flux manifest construction** (render mode):
   - `HelmRepository` manifest
   - `Namespace` manifest
   - `HelmRelease` manifest with values
   - `Kustomization` manifest
6. **Apply-mode resources** (guarded by `count`):
   - `kubernetes_namespace.external_dns[0]`
   - `helm_release.external_dns[0]`

Key Helm values to template:

```hcl
default_values_map = {
  provider = {
    name = "cloudflare"
  }
  env = [
    {
      name = "CF_API_TOKEN"
      valueFrom = {
        secretKeyRef = {
          name = local.cloudflare_api_token_secret_name
          key  = local.cloudflare_api_token_secret_key
        }
      }
    }
  ]
  domainFilters = var.domain_filters
  policy        = local.policy
  txtOwnerId    = local.txt_owner_id
  sources       = var.sources
  extraArgs = concat(
    var.cloudflare_proxied ? ["--cloudflare-proxied"] : [],
    ["--cloudflare-dns-records-per-page=${var.dns_records_per_page}"]
  )
  crd = {
    create = var.crd_enabled
  }
  serviceMonitor = {
    enabled = var.service_monitor_enabled
  }
}
```

Rendered manifests output (render mode):

```hcl
rendered_manifests = merge(
  {
    "platform/sources/external-dns-repo.yaml" = yamlencode(flux_helm_repository_manifest)
    "platform/external-dns/namespace.yaml"    = yamlencode(namespace_manifest)
    "platform/external-dns/helmrelease.yaml"  = yamlencode(flux_helmrelease_manifest)
    "platform/external-dns/kustomization.yaml" = yamlencode(kustomization_manifest)
  }
)
```

#### 1.4 `outputs.tf`

| Output               | Description                                   |
| -------------------- | --------------------------------------------- |
| `namespace`          | Namespace where ExternalDNS is installed      |
| `helm_release_name`  | Name of the Helm release                      |
| `txt_owner_id`       | Ownership ID for DNS records                  |
| `domain_filters`     | List of managed domains                       |
| `rendered_manifests` | Map of GitOps path -> YAML (render mode only) |

### Step 2: Create Examples

#### 2.1 `examples/basic/` (Apply Mode)

- Requires `kubeconfig_path` variable with file existence check
- Instantiates module with `mode = "apply"`
- Forwards key outputs

#### 2.2 `examples/render/` (Render Mode)

- No cluster connection required
- Instantiates module with `mode = "render"`
- Outputs `rendered_manifests` map

### Step 3: Create OPA Policies

#### 3.1 `policy/manifests/helmrelease.rego`

Validate rendered HelmRelease:

- Must pin `chart.spec.version`
- Must set `chart.spec.sourceRef.name` and `namespace`
- Must set `domainFilters` (non-empty)
- Must set `txtOwnerId` (non-empty)
- Must set `policy` to `sync` or `upsert-only`
- Warn if using insecure HTTP for HelmRepository URL

#### 3.2 `policy/plan/externaldns.rego`

Validate Terraform plan:

- Helm release must have valid provider configuration
- Secret reference must be present
- Domain filters must not be empty

### Step 4: Create Terratest Integration Tests

`tests/external_dns_test.go`:

1. **TestExternalDNSModuleValidate**: Init and validate basic example
2. **TestExternalDNSModuleRenderOutputs**: Apply render example, verify outputs
3. **TestExternalDNSModuleRenderPolicy**: Run conftest against rendered
   manifests
4. **TestExternalDNSModuleInvalidInputs**: Table-driven validation tests
   - Invalid namespace format
   - Empty domain filters
   - Invalid policy value
   - Blank txt_owner_id
   - Invalid chart version format
5. **TestExternalDNSModuleNullVariableValidation**: Null input handling
6. **TestExternalDNSModulePlanDetailedExitCode**: Detailed exit code with
   kubeconfig
7. **TestExternalDNSModulePolicy**: Conftest against plan JSON
8. **TestExternalDNSModuleApplyIfKubeconfigPresent**: Full apply test (gated)

Use `testutil.SetupTerraform()` helper for consistent test setup.

### Step 5: Update Makefile

Add targets:

```makefile
external-dns-test:
	tofu fmt -check infra/modules/external_dns
	tofu -chdir=infra/modules/external_dns/examples/render init
	tofu -chdir=infra/modules/external_dns/examples/render validate
	TF_IN_AUTOMATION=1 tofu -chdir=infra/modules/external_dns/examples/render plan \
		-input=false -no-color -detailed-exitcode || test $$? -eq 2
	tofu -chdir=infra/modules/external_dns/examples/basic init
	# Conditional validation/plan with EXTERNAL_DNS_KUBECONFIG_PATH
	command -v tflint >/dev/null
	cd infra/modules/external_dns && tflint --init && tflint --config .tflint.hcl
	cd infra/modules/external_dns/tests && $(GO_TEST_ENV) go test -v
	$(MAKE) external-dns-policy

external-dns-policy: conftest tofu
	./scripts/external-dns-render-policy.sh
	# Conditional plan-based policy check with kubeconfig
```

Add to `INFRA_TEST_TARGETS` and `lint-infra`.

### Step 6: Create Supporting Scripts

#### 6.1 `scripts/external-dns-render-policy.sh`

Runs conftest against rendered manifests from the render example.

### Step 7: Create Documentation

#### 7.1 `README.md`

Document:

- Prerequisites (Kubernetes cluster, cert-manager, Cloudflare secret)
- Usage examples (apply and render modes)
- Input variables table
- Outputs table
- Integration with FluxCD GitOps workflow
- Cloudflare API token permissions required
- Troubleshooting common issues

### Step 8: Update Roadmap

Update `docs/ephemeral-previews-roadmap.md`:

- Mark ExternalDNS module task as complete: `[x]`

## Testing Strategy

### Static Analysis

- `tofu fmt -check`: Formatting
- `tofu validate`: Configuration validity
- `tflint`: Best practices
- `checkov`: Security scanning (via `lint-infra`)

### Unit Tests (Terratest)

- Validate module configuration
- Test input validation error messages
- Test rendered manifest structure
- Test apply-mode resource creation (with kubeconfig)

### Policy Tests (OPA/Conftest)

- Rendered manifest validation
- Plan-time policy checks

### Integration Tests

- Full apply/destroy cycle (gated by env vars)
- Verify Helm release creation
- Verify namespace creation

## Quality Gates

Before committing:

- `make check-fmt` passes
- `make lint` passes (includes `lint-infra`)
- `make external-dns-test` passes
- All Terratest tests pass
- All policy tests pass

## Critical Files to Modify

New files:

- `infra/modules/external_dns/main.tf`
- `infra/modules/external_dns/variables.tf`
- `infra/modules/external_dns/outputs.tf`
- `infra/modules/external_dns/versions.tf`
- `infra/modules/external_dns/README.md`
- `infra/modules/external_dns/.tflint.hcl`
- `infra/modules/external_dns/policy/manifests/helmrelease.rego`
- `infra/modules/external_dns/policy/plan/externaldns.rego`
- `infra/modules/external_dns/examples/basic/main.tf`
- `infra/modules/external_dns/examples/basic/variables.tf`
- `infra/modules/external_dns/examples/basic/outputs.tf`
- `infra/modules/external_dns/examples/render/main.tf`
- `infra/modules/external_dns/examples/render/variables.tf`
- `infra/modules/external_dns/examples/render/outputs.tf`
- `infra/modules/external_dns/tests/external_dns_test.go`
- `infra/modules/external_dns/tests/go.mod`
- `infra/modules/external_dns/tests/go.sum`
- `scripts/external-dns-render-policy.sh`

Modified files:

- `Makefile` (add `external-dns-test`, `external-dns-policy` targets)
- `docs/ephemeral-previews-roadmap.md` (mark task complete)

## Design Decisions

1. **Module naming**: Use `external_dns` (snake_case) to match existing modules
   (`vault_appliance`).

2. **Provider**: Focus on Cloudflare as primary provider per project
   requirements.
   The module structure supports future extension to other providers.

3. **Mode switching**: Follow Traefik pattern with `mode = "render"` (default)
   and
   `mode = "apply"` for consistency.

4. **Helm chart source**: Use official `kubernetes-sigs` chart repository for
   ExternalDNS.

5. **Default policy**: Use `sync` policy (create, update, delete) rather than
   `upsert-only` to ensure proper cleanup of stale records.

6. **Ownership tracking**: Require `txt_owner_id` to prevent conflicts between
   multiple ExternalDNS instances managing the same zones.

7. **API rate limiting**: Default `dns_records_per_page` to 5000 to mitigate
   Cloudflare API rate limits.
