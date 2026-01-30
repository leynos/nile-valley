# Documentation index

## Platform overview

- [Cloud-native architecture for preview environments](cloud-native-ephemeral-previews.md)
  – GitOps-driven preview platform design. *Audience: platform engineers.*
- [Ephemeral previews infrastructure roadmap](ephemeral-previews-roadmap.md)
  – phased plan for preview environment infrastructure. *Audience: platform
  engineers and project managers.*
- [Repository design guide](repository-structure.md) – explains repository
  layout and automation flow. *Audience: new contributors.*

## Infrastructure modules and patterns

- [DOKS OpenTofu module design](doks-module-design.md) – design decisions for
  the DigitalOcean Kubernetes module. *Audience: infrastructure developers.*
- [FluxCD OpenTofu module design](fluxcd-module-design.md) – design decisions
  for the GitOps control plane module. *Audience: infrastructure developers.*
- [Cert-manager OpenTofu module design](cert-manager-module-design.md) –
  design decisions for the cert-manager module. *Audience: infrastructure
  developers.*
- [Vault appliance OpenTofu module design](vault-appliance-module-design.md) –
  design decisions for the Vault infrastructure module. *Audience:
  infrastructure developers.*
- [Vault External Secrets Operator (ESO) OpenTofu module design](vault-eso-module-design.md)
  – design decisions for the ESO integration module. *Audience:
  infrastructure developers.*
- [Valkey OpenTofu module design](valkey-module-design.md) – design decisions
  for the Valkey (Redis-compatible) module. *Audience: infrastructure
  developers.*
- [OpenTofu module interoperability contract](opentofu-module-interoperability-contract.md)
  – defines how modules thread DNS zones, issuers, and credential handles.
  *Audience: infrastructure developers.*

## Infrastructure guides

- [OpenTofu coding standards](opentofu-coding-standards.md) – conventions for
  IaC authoring. *Audience: infrastructure developers.*
- [A comprehensive developer’s guide to HCL for OpenTofu](opentofu-hcl-syntax-guide.md)
  – HCL syntax and workflows. *Audience: infrastructure developers.*
- [Unit testing OpenTofu modules and scripts](opentofu-module-unit-testing-guide.md)
  – strategies for testing IaC modules. *Audience: infrastructure developers.*
- [OpenTofu state backend guide](opentofu-state-backend.md) – configuring the
  shared state backend. *Audience: infrastructure developers.*
- [Declarative DNS guide](declarative-dns-guide.md) – automating Cloudflare DNS
  with FluxCD, ExternalDNS, and OpenTofu. *Audience: platform engineers.*
- [Declarative TLS guide](declarative-tls-guide.md) – automating certificate
  management with cert-manager. *Audience: platform engineers.*
- [Using Cloudflare DNS with OpenTofu](using-cloudflare-dns-with-opentofu.md)
  – practical steps for managing DNS records. *Audience: infrastructure
  developers.*
- [Infrastructure test dependency checklist](infrastructure-test-dependencies.md)
  – validates CLI prerequisites before running policy suites. *Audience:
  infrastructure developers and CI engineers.*
- [Local validation of GitHub Actions with act and pytest](local-validation-of-github-actions-with-act-and-pytest.md)
  – workflow test harness guidance. *Audience: automation authors.*

## Runbooks

- [Session signing key rotation](runbooks/session-key-rotation.md) – rotate the
  session signing key for applications using the example chart. *Audience:
  platform engineers and app operators.*

## Developer guidelines and tooling

- [Documentation style guide](documentation-style-guide.md) – conventions for
  clear, consistent docs. *Audience: all contributors.*
- [Scripting standards](scripting-standards.md) – Python-first automation
  guidance covering `uv`, `plumbum`, and testing expectations. *Audience:
  automation authors.*
- [cmd-mox users guide](cmd-mox-users-guide.md) – mocking CLI tools in Python
  tests. *Audience: automation authors.*
- [Complexity antipatterns and refactoring strategies](complexity-antipatterns-and-refactoring-strategies.md)
  – managing code complexity. *Audience: implementers and maintainers.*
- [Biome configuration schema](biome-schema.json) – JSON schema for
  `biome.json`. *Audience: contributors editing Biome settings.*
