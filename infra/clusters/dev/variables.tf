# Input variables for the dev cluster root configuration.
# Defaults provision a small two-node cluster in nyc1 for preview workloads.

variable "should_create_cluster" {
  type        = bool
  description = "Whether to create the dev cluster"
  default     = false
}

variable "cluster_name" {
  type        = string
  description = "Name for the DOKS cluster"
  default     = "nile-valley-dev"

  validation {
    condition     = length(trimspace(var.cluster_name)) > 0
    error_message = "cluster_name must not be blank"
  }
}

variable "region" {
  type        = string
  description = "DigitalOcean region slug"
  default     = "nyc1"

  validation {
    condition     = can(regex("^[a-z]{3}[0-9]$", var.region))
    error_message = "region must be a 3-letter region code followed by a digit (e.g., nyc1, sfo3, ams3)."
  }
}

variable "node_pools" {
  type = list(object({
    name       = string
    size       = string
    node_count = number
    auto_scale = bool
    min_nodes  = number
    max_nodes  = number
    tags       = optional(list(string))
  }))
  description = "List of node pool definitions"

  validation {
    condition = alltrue([
      for p in var.node_pools :
      p.node_count >= 2 &&
      (
        p.auto_scale
        ? (
          p.min_nodes >= 2 &&
          p.max_nodes >= p.min_nodes &&
          p.node_count >= p.min_nodes &&
          p.node_count <= p.max_nodes
        )
        : (
          p.min_nodes == p.node_count &&
          p.max_nodes == p.node_count
        )
      )
    ])
    error_message = "Each node pool must have at least 2 nodes. When auto_scale is true, min_nodes must be less than or equal to node_count, and node_count must be between min_nodes and max_nodes. When auto_scale is false, min_nodes and max_nodes must equal node_count."
  }
  default = [
    {
      name       = "default"
      size       = "s-2vcpu-2gb"
      node_count = 2
      auto_scale = false
      min_nodes  = 2
      max_nodes  = 2
      tags       = ["env:dev"]
    }
  ]
}

variable "tags" {
  type        = list(string)
  description = "Tags applied to the cluster"
  default     = ["env:dev"]

  validation {
    condition     = length(var.tags) > 0
    error_message = "tags must contain at least one value"
  }

  validation {
    condition     = alltrue([for t in var.tags : length(trimspace(t)) > 0])
    error_message = "tags must not be blank strings"
  }

  validation {
    condition     = length(distinct([for t in var.tags : trimspace(t)])) == length(var.tags)
    error_message = "tags must be unique after trimming whitespace"
  }
}

variable "expose_kubeconfig" {
  type        = bool
  description = "Expose kubeconfig via module outputs (stores credentials in state)"
  default     = false
}

variable "flux" {
  description = "Flux configuration for the dev cluster"
  type = object({
    install           = bool
    kubeconfig_path   = string
    allow_file_scheme = bool
    namespace         = string
    git_repository = object({
      name        = string
      url         = optional(string)
      branch      = string
      path        = string
      secret_name = optional(string)
    })
    reconcile_interval = string
    kustomization = object({
      name    = string
      prune   = bool
      suspend = bool
      timeout = string
    })
    helm = object({
      release_name = string
      repository   = string
      chart        = string
      version      = string
      wait         = bool
      timeout      = number
      values       = optional(list(string), [])
      values_files = optional(list(string), [])
    })
  })
  default = {
    install           = false
    kubeconfig_path   = ""
    allow_file_scheme = false
    namespace         = "flux-system"
    git_repository = {
      name        = "flux-system"
      url         = null
      branch      = "main"
      path        = "./clusters/dev"
      secret_name = null
    }
    reconcile_interval = "1m"
    kustomization = {
      name    = "flux-system"
      prune   = true
      suspend = false
      timeout = "5m"
    }
    helm = {
      release_name = "flux-system"
      repository   = "https://fluxcd-community.github.io/helm-charts"
      chart        = "flux2"
      version      = "2.16.4"
      wait         = true
      timeout      = 600
      values       = []
      values_files = []
    }
  }

  validation {
    condition = (
      !var.flux.install ||
      var.should_create_cluster ||
      length(trimspace(var.flux.kubeconfig_path)) > 0
    )
    error_message = "flux.install requires should_create_cluster to be true or flux.kubeconfig_path to be set"
  }

  validation {
    condition = (
      length(trimspace(var.flux.namespace)) > 0 &&
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.flux.namespace)) &&
      length(var.flux.namespace) <= 63
    )
    error_message = "flux.namespace must be a valid Kubernetes namespace name"
  }

  validation {
    condition     = length(trimspace(var.flux.git_repository.name)) > 0
    error_message = "flux.git_repository.name must not be blank"
  }

  validation {
    condition     = length(trimspace(var.flux.kustomization.name)) > 0
    error_message = "flux.kustomization.name must not be blank"
  }

  validation {
    condition = (
      !var.flux.install || (
        length(trimspace(coalesce(var.flux.git_repository.url, ""))) > 0 &&
        (
          can(regex("^(https://|ssh://|git@)", coalesce(var.flux.git_repository.url, ""))) ||
          (
            var.flux.allow_file_scheme &&
            can(regex("^file://", coalesce(var.flux.git_repository.url, "")))
          )
        )
      )
    )
    error_message = "flux.git_repository.url must be HTTPS, SSH, or git@. Set allow_file_scheme=true to permit file:// URLs"
  }

  validation {
    condition     = (!var.flux.install) || length(trimspace(var.flux.git_repository.branch)) > 0
    error_message = "flux.git_repository.branch must not be blank when installing Flux"
  }

  validation {
    condition = (
      !var.flux.install || (
        length(trimspace(var.flux.git_repository.path)) > 0 &&
        (
          trimspace(var.flux.git_repository.path) == "." ||
          startswith(trimspace(var.flux.git_repository.path), "./")
        ) &&
        length(regexall("\\.\\.", trimspace(var.flux.git_repository.path))) == 0
      )
    )
    error_message = "flux.git_repository.path must be a non-empty relative path without traversal when installing Flux"
  }

  validation {
    condition = (
      var.flux.git_repository.secret_name == null ||
      length(trimspace(var.flux.git_repository.secret_name)) > 0
    )
    error_message = "flux.git_repository.secret_name must not be blank when set"
  }

  validation {
    condition     = (!var.flux.install) || can(regex("^([0-9]+(s|m|h|d|w))+$", trimspace(var.flux.reconcile_interval)))
    error_message = "flux.reconcile_interval must be a valid duration string"
  }

  validation {
    condition     = (!var.flux.install) || can(regex("^([0-9]+(s|m|h|d|w))+$", trimspace(var.flux.kustomization.timeout)))
    error_message = "flux.kustomization.timeout must be a valid duration string"
  }

  validation {
    condition     = var.flux.helm.timeout > 0
    error_message = "flux.helm.timeout must be a positive number of seconds"
  }

  validation {
    condition = alltrue([
      for path in var.flux.helm.values_files : length(trimspace(path)) > 0
    ])
    error_message = "flux.helm.values_files must not contain blank file paths"
  }
}
