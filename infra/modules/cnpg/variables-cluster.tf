variable "cluster_name" {
  description = "Name of the CNPG Cluster resource"
  type        = string
  default     = "nile-valley-pg-main"

  validation {
    condition = (
      var.cluster_name != null &&
      length(trimspace(var.cluster_name)) > 0 &&
      length(trimspace(var.cluster_name)) <= 63 &&
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", trimspace(var.cluster_name)))
    )
    error_message = "cluster_name must be a valid Kubernetes resource name"
  }
}

variable "instances" {
  description = "Number of PostgreSQL instances (1 primary + N-1 replicas)"
  type        = number
  default     = 3
  nullable    = false

  validation {
    condition     = var.instances > 0
    error_message = "instances must be greater than zero"
  }
}

variable "image_name" {
  description = "PostgreSQL container image (should include PostGIS if postgis_enabled)"
  type        = string
  default     = "ghcr.io/cloudnative-pg/postgis:16-3.4"

  validation {
    condition     = var.image_name != null && length(trimspace(var.image_name)) > 0
    error_message = "image_name must not be blank"
  }
}

variable "storage_size" {
  description = "PVC storage size for each PostgreSQL instance"
  type        = string
  default     = "50Gi"

  validation {
    condition = (
      var.storage_size != null &&
      can(regex("^[0-9]+(Ki|Mi|Gi|Ti|Pi|Ei)$", trimspace(var.storage_size)))
    )
    error_message = "storage_size must be a valid Kubernetes quantity with unit suffix (e.g., 50Gi, 100Gi)"
  }
}

variable "storage_class" {
  description = "Kubernetes StorageClass for PostgreSQL PVCs"
  type        = string
  default     = "do-block-storage"

  validation {
    condition     = var.storage_class != null && length(trimspace(var.storage_class)) > 0
    error_message = "storage_class must not be blank"
  }
}

variable "database_name" {
  description = "Initial database name to create"
  type        = string
  default     = "nile_valley_prod"

  validation {
    condition = (
      var.database_name != null &&
      length(trimspace(var.database_name)) > 0 &&
      can(regex("^[a-z_][a-z0-9_]*$", trimspace(var.database_name)))
    )
    error_message = "database_name must be a valid PostgreSQL identifier"
  }
}

variable "database_owner" {
  description = "Owner username for the initial database"
  type        = string
  default     = "nile_valley_user"

  validation {
    condition = (
      var.database_owner != null &&
      length(trimspace(var.database_owner)) > 0 &&
      can(regex("^[a-z_][a-z0-9_]*$", trimspace(var.database_owner)))
    )
    error_message = "database_owner must be a valid PostgreSQL identifier"
  }
}

variable "postgis_enabled" {
  description = "Whether to install PostGIS extensions during database bootstrap"
  type        = bool
  default     = true
  nullable    = false
}

variable "primary_update_strategy" {
  description = "Primary update strategy (unsupervised or supervised)"
  type        = string
  default     = "unsupervised"
  nullable    = false

  validation {
    condition     = contains(["unsupervised", "supervised"], trimspace(var.primary_update_strategy))
    error_message = "primary_update_strategy must be one of: unsupervised, supervised"
  }
}

variable "primary_update_method" {
  description = "Primary update method (switchover or restart)"
  type        = string
  default     = "switchover"
  nullable    = false

  validation {
    condition     = contains(["switchover", "restart"], trimspace(var.primary_update_method))
    error_message = "primary_update_method must be one of: switchover, restart"
  }
}

variable "postgresql_parameters" {
  description = "Custom PostgreSQL configuration parameters"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "resource_requests" {
  description = "Resource requests for each PostgreSQL pod"
  type = object({
    cpu    = string
    memory = string
  })
  default = {
    cpu    = "100m"
    memory = "256Mi"
  }
  nullable = false

  validation {
    condition = (
      can(regex("^[0-9]+(\\.[0-9]+)?m?$", trimspace(var.resource_requests.cpu)))
    )
    error_message = "resource_requests.cpu must be a valid Kubernetes CPU quantity (e.g., 100m, 0.5, 2)"
  }

  validation {
    condition = (
      can(regex("^[0-9]+(Ki|Mi|Gi|Ti|Pi|Ei)$", trimspace(var.resource_requests.memory)))
    )
    error_message = "resource_requests.memory must be a valid Kubernetes memory quantity (e.g., 256Mi, 1Gi)"
  }
}

variable "resource_limits" {
  description = "Resource limits for each PostgreSQL pod"
  type = object({
    cpu    = string
    memory = string
  })
  default = {
    cpu    = "2"
    memory = "2Gi"
  }
  nullable = false

  validation {
    condition = (
      can(regex("^[0-9]+(\\.[0-9]+)?m?$", trimspace(var.resource_limits.cpu)))
    )
    error_message = "resource_limits.cpu must be a valid Kubernetes CPU quantity (e.g., 100m, 0.5, 2)"
  }

  validation {
    condition = (
      can(regex("^[0-9]+(Ki|Mi|Gi|Ti|Pi|Ei)$", trimspace(var.resource_limits.memory)))
    )
    error_message = "resource_limits.memory must be a valid Kubernetes memory quantity (e.g., 256Mi, 1Gi)"
  }
}

variable "pdb_enabled" {
  description = "Whether to render/apply PodDisruptionBudget for the cluster"
  type        = bool
  default     = true
  nullable    = false
}

variable "pdb_min_available" {
  description = "Minimum available pods for the cluster PDB"
  type        = number
  default     = 1
  nullable    = false

  validation {
    condition     = var.pdb_min_available > 0
    error_message = "pdb_min_available must be greater than zero"
  }
}

variable "pdb_name" {
  description = "Name of the PodDisruptionBudget for the PostgreSQL cluster"
  type        = string
  default     = "cnpg-cluster-pdb"

  validation {
    condition     = var.pdb_name != null && length(trimspace(var.pdb_name)) > 0
    error_message = "pdb_name must not be blank"
  }
}
