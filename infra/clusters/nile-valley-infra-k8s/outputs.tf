# Output values for the nile-valley-infra-k8s cluster configuration.
#
# These outputs are exposed to the nile-valley-infra-k8s GitHub Action for
# publishing cluster information and kubeconfig to downstream consumers.

# -----------------------------------------------------------------------------
# Cluster Outputs
# -----------------------------------------------------------------------------

output "cluster_id" {
  description = "Identifier of the DigitalOcean Kubernetes cluster"
  value       = module.doks.cluster_id
}

output "endpoint" {
  description = "API server endpoint for the Kubernetes cluster"
  value       = module.doks.endpoint
}

output "kubeconfig" {
  description = "Raw kubeconfig for cluster access (sensitive)"
  sensitive   = true
  value       = module.doks.kubeconfig
}

# -----------------------------------------------------------------------------
# FluxCD Outputs
# -----------------------------------------------------------------------------

output "flux_namespace" {
  description = "Namespace where Flux components are installed"
  value       = local.should_configure_flux ? module.fluxcd[0].namespace : null
}

output "flux_git_repository_name" {
  description = "Name of the GitRepository resource managed by FluxCD"
  value       = local.should_configure_flux ? module.fluxcd[0].git_repository_name : null
}

output "flux_kustomization_name" {
  description = "Name of the Kustomization resource managed by FluxCD"
  value       = local.should_configure_flux ? module.fluxcd[0].kustomization_name : null
}
