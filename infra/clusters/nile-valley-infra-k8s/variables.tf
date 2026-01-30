# Input variables for the nile-valley-infra-k8s cluster configuration.
#
# These variables are passed by the nile-valley-infra-k8s GitHub Action when
# provisioning or updating cluster infrastructure.

# -----------------------------------------------------------------------------
# Cluster Configuration
# -----------------------------------------------------------------------------

variable "cluster_name" {
  description = "Name for the DigitalOcean Kubernetes cluster"
  type        = string

  validation {
    condition     = length(trimspace(var.cluster_name)) > 0
    error_message = "cluster_name must not be blank"
  }

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", trimspace(var.cluster_name)))
    error_message = "cluster_name must contain only lowercase letters, numbers, and hyphens"
  }
}

variable "region" {
  description = "DigitalOcean region slug (e.g., nyc1, sfo3, ams3)"
  type        = string

  validation {
    condition     = can(regex("^[a-z]{3}[0-9]$", var.region))
    error_message = "region must be a valid DigitalOcean slug (e.g., nyc1)"
  }
}

variable "kubernetes_version" {
  description = "Kubernetes version for the cluster (e.g., 1.33.1-do.3)"
  type        = string
  default     = null

  validation {
    condition = (
      var.kubernetes_version == null ||
      can(regex("^\\d+\\.\\d+\\.\\d+-do\\.\\d+$", var.kubernetes_version))
    )
    error_message = "kubernetes_version must match '<major>.<minor>.<patch>-do.<n>'"
  }
}

variable "node_pools" {
  description = "List of node pool configurations"
  type = list(object({
    name       = string
    size       = string
    node_count = number
    auto_scale = bool
    min_nodes  = number
    max_nodes  = number
    tags       = optional(list(string))
  }))

  validation {
    condition     = length(var.node_pools) > 0
    error_message = "node_pools must contain at least one pool"
  }

  validation {
    condition = alltrue([
      for np in var.node_pools :
      np.min_nodes >= 1 &&
      np.min_nodes <= np.node_count &&
      np.node_count <= np.max_nodes
    ])
    error_message = "each node pool must satisfy min_nodes >= 1 and min_nodes <= node_count <= max_nodes"
  }

  validation {
    condition = alltrue([
      for np in var.node_pools :
      np.auto_scale ? (np.min_nodes >= 2) : (np.node_count >= 2)
    ])
    error_message = "each node pool must have node_count >= 2 (or min_nodes >= 2 when auto_scale is true)"
  }
}

variable "tags" {
  description = "Tags applied to the cluster and its resources"
  type        = list(string)
  default     = []
}

variable "expose_kubeconfig" {
  description = "Expose kubeconfig via outputs (stores credentials in state)"
  type        = bool
  default     = true
}

# Note: Cluster destruction protection is enforced at the workflow level via
# GitHub Actions inputs and concurrency controls, not at the Terraform level.
# See main.tf comments for details.

# -----------------------------------------------------------------------------
# FluxCD Configuration
# -----------------------------------------------------------------------------

variable "flux_install" {
  description = "Whether to install FluxCD on the cluster"
  type        = bool
  default     = false
}

variable "flux_kubeconfig_path" {
  description = "Path to kubeconfig for FluxCD installation"
  type        = string
  default     = null

  validation {
    condition = (
      var.flux_kubeconfig_path == null ||
      length(trimspace(var.flux_kubeconfig_path)) > 0
    )
    error_message = "flux_kubeconfig_path must not be blank when set"
  }
}

variable "flux_namespace" {
  description = "Namespace where Flux controllers are installed"
  type        = string
  default     = "flux-system"

  validation {
    condition = (
      length(trimspace(var.flux_namespace)) > 0 &&
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.flux_namespace)) &&
      length(var.flux_namespace) <= 63
    )
    error_message = "flux_namespace must be a valid Kubernetes namespace name"
  }
}

variable "flux_git_repository_url" {
  description = "URL of the Git repository containing Flux manifests"
  type        = string
  default     = null

  validation {
    condition = (
      var.flux_git_repository_url == null ||
      can(regex("^(https://|ssh://|git@)", var.flux_git_repository_url))
    )
    error_message = "flux_git_repository_url must be HTTPS, SSH, or git@ URL"
  }
}

variable "flux_git_repository_branch" {
  description = "Branch of the Git repository to sync"
  type        = string
  default     = "main"

  validation {
    condition     = length(trimspace(var.flux_git_repository_branch)) > 0
    error_message = "flux_git_repository_branch must not be blank"
  }
}

variable "flux_git_repository_path" {
  description = "Path within the Git repository for the cluster root"
  type        = string
  default     = "."

  validation {
    condition = (
      trimspace(var.flux_git_repository_path) == "." ||
      (
        length(trimspace(var.flux_git_repository_path)) > 0 &&
        !startswith(trimspace(var.flux_git_repository_path), "/")
      )
    )
    error_message = "flux_git_repository_path must be a valid relative path"
  }
}

variable "flux_git_repository_secret_name" {
  description = "Kubernetes secret name providing Git credentials"
  type        = string
  default     = null

  validation {
    condition = (
      var.flux_git_repository_secret_name == null ||
      length(trimspace(var.flux_git_repository_secret_name)) > 0
    )
    error_message = "flux_git_repository_secret_name must not be blank when set"
  }
}
