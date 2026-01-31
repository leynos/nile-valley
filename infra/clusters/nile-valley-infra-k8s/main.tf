# Wildside Infrastructure Kubernetes Cluster Provisioning
#
# Provisions a DigitalOcean Kubernetes cluster and bootstraps FluxCD for GitOps.
# This configuration is invoked by the nile-valley-infra-k8s GitHub Action to
# assemble cluster infrastructure and commit manifests to the GitOps repository.
#
# State is stored in DigitalOcean Spaces via the S3-compatible backend. Each
# cluster uses a separate state file, isolated by the workspace or key parameter.

terraform {
  required_version = ">= 1.6"

  backend "s3" {
    # Backend configuration is provided at init time via:
    #   tofu init -backend-config=../../backend-config/spaces.tfbackend \
    #             -backend-config="access_key=$SPACES_ACCESS_KEY" \
    #             -backend-config="secret_key=$SPACES_SECRET_KEY" \
    #             -backend-config="key=clusters/${CLUSTER_NAME}/terraform.tfstate"
  }
}

provider "digitalocean" {
  # Token is read from DIGITALOCEAN_TOKEN environment variable.
}

locals {
  cluster_name_normalised = trimspace(var.cluster_name)
  region_normalised       = trimspace(var.region)
  tags_normalised         = distinct(compact([for t in var.tags : trimspace(t)]))

  node_pools_normalised = [
    for np in var.node_pools : merge(np, {
      tags = try(distinct(compact([for t in np.tags : trimspace(t)])), null)
    })
  ]

  # FluxCD configuration normalisation
  flux_config = {
    install         = var.flux_install
    # Coalesce null to blank so trimspace yields "" for local.flux_config.kubeconfig_path,
    # which flux_using_kubeconfig relies on.
    kubeconfig_path = trimspace(coalesce(var.flux_kubeconfig_path, " "))
    namespace       = trimspace(var.flux_namespace)
    git_repository = {
      url         = var.flux_git_repository_url == null ? null : trimspace(var.flux_git_repository_url)
      branch      = trimspace(var.flux_git_repository_branch)
      path        = trimspace(var.flux_git_repository_path)
      secret_name = var.flux_git_repository_secret_name == null ? null : trimspace(var.flux_git_repository_secret_name)
    }
  }

  # Flux can only be configured when we have a kubeconfig to connect with.
  flux_using_kubeconfig = local.flux_config.kubeconfig_path != ""
  should_configure_flux = local.flux_config.install && local.flux_using_kubeconfig
}

# Cluster destruction protection is enforced at the workflow level:
# - GitHub Actions require explicit "destroy" mode input
# - Concurrency groups prevent parallel operations on the same cluster
# - State isolation ensures operations only affect the target cluster
module "doks" {
  source = "../../modules/doks"

  cluster_name       = local.cluster_name_normalised
  region             = local.region_normalised
  kubernetes_version = var.kubernetes_version
  node_pools         = local.node_pools_normalised
  tags               = local.tags_normalised
  expose_kubeconfig  = var.expose_kubeconfig
}

# Kubernetes provider for FluxCD bootstrap
provider "kubernetes" {
  alias       = "flux"
  config_path = local.flux_using_kubeconfig ? local.flux_config.kubeconfig_path : null
}

provider "helm" {
  alias = "flux"

  kubernetes {
    config_path = local.flux_using_kubeconfig ? local.flux_config.kubeconfig_path : null
  }
}

module "fluxcd" {
  count  = local.should_configure_flux ? 1 : 0
  source = "../../modules/fluxcd"

  providers = {
    kubernetes = kubernetes.flux
    helm       = helm.flux
  }

  namespace                  = local.flux_config.namespace
  git_repository_url         = local.flux_config.git_repository.url
  git_repository_branch      = local.flux_config.git_repository.branch
  git_repository_path        = local.flux_config.git_repository.path
  git_repository_secret_name = local.flux_config.git_repository.secret_name
}

# Validation check to ensure Flux has an authentication source when requested
check "flux_authentication_source" {
  assert {
    condition     = !local.flux_config.install || local.flux_using_kubeconfig
    error_message = "Flux install requires flux_kubeconfig_path to reference a readable kubeconfig."
  }
}
