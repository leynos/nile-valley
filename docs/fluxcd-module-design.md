# FluxCD OpenTofu module design

This document records the design decisions behind the FluxCD module that
installs the GitOps control plane for Nile Valley's ephemeral preview platform.

## Overview

The module installs Flux via the community `flux2` Helm chart and provisions
GitOps primitives (a `GitRepository` and `Kustomization`) so the cluster
immediately begins reconciling the desired state stored in Git. The module is
meant to run against an existing Kubernetes cluster provisioned by the DOKS
module.

## Design decisions

- **Helm-driven installation.** The module uses the `flux2` chart from the
  `fluxcd-community` repository. Helm handles controller lifecycle management,
  CRD installation, and upgrades while leaving Git integration to native Flux
  custom resources created via the Kubernetes provider.
- **Declarative GitOps bootstrap.** The module defines a Flux `GitRepository`
  and `Kustomization` resource. This mirrors the `flux bootstrap` workflow
  without shelling out to the Flux CLI. The resources are parameterized so the
  Git URL, branch, and repository path are supplied by callers.
- **Safe defaults.** Reconciliation runs every minute, pruning is enabled, and
  the module prevents suspended Kustomizations or absolute repository paths via
  input validation and OPA policies. Optional inputs allow callers to supply a
  Kubernetes secret for private repositories.
- **Helm overrides as inputs.** The `helm_values` and `helm_values_files`
  variables expose Flux chart customization without forcing consumers to wrap
  the module or fork the Helm release configuration.
- **Dual authentication paths.** The parent configuration may either provide a
  kubeconfig path or allow the module to derive credentials from the DOKS API.
  When credentials are fetched remotely, the module decodes the DigitalOcean
  cluster's CA certificate and token and wires them into aliased Helm and
  Kubernetes providers.
- **Policy enforcement.** A Conftest policy ensures Git URLs use an accepted
  scheme, reconciliation intervals stay within seconds or minutes, pruning is
  enabled, and the Kustomization references a GitRepository source. This aligns
  with the GitOps conventions defined for Nile Valley.
- **Testing strategy.** Terratest covers validation failures, provider errors
  (missing kubeconfig), detailed exit codes, Conftest enforcement, and a gated
  apply flow that runs only when `FLUXCD_ACCEPT_APPLY` and `KUBECONFIG` are
  set. Tests reuse the shared `infra/testutil` helpers for consistency across
  modules.

## Integration with the dev cluster configuration

- **Structured Flux input.** `infra/clusters/dev` now accepts a `flux` object
  combining the install toggle, Git metadata, Helm settings, and kubeconfig
  source. When `flux.install` is true the configuration instantiates the module
  and configures Helm/Kubernetes providers using either an operator-supplied
  kubeconfig file or the cluster credentials fetched from DigitalOcean.
- **Validations.** The root module validates that enabling Flux requires a DOKS
  cluster (or kubeconfig path) and ensures the object attributes, such as the
  Git URL and repository path, remain policy compliant. Tests assert these
  guard rails.
- **Outputs.** The dev configuration exports the Flux namespace, Git repository
  name, and Kustomization name to simplify downstream automation.

## Future work

- Surface additional Flux configuration (notification controllers, image
  automation) as optional inputs once the GitOps tree is fully modelled.
- Expand policy coverage to assert tighter reconciliation SLAs or enforce
  multi-tenancy lockdown once platform requirements are finalized.
