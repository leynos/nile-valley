# Input variables for the platform_render orchestration module.
#
# This module wires all platform modules together in render mode, producing a
# unified set of Flux-ready manifests for GitOps workflows.

# -----------------------------------------------------------------------------
# Core Configuration
# -----------------------------------------------------------------------------

variable "cluster_name" {
  description = "Name of the Kubernetes cluster (used for resource naming)"
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.cluster_name)) > 0
    error_message = "cluster_name must not be blank"
  }

  validation {
    condition     = length(trimspace(var.cluster_name)) <= 63
    error_message = "cluster_name must be 63 characters or fewer"
  }

  validation {
    condition = can(regex(
      "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
      trimspace(var.cluster_name)
    ))
    error_message = "cluster_name must contain only lowercase letters, numbers, and hyphens"
  }
}

variable "domain" {
  description = "Root DNS domain for the cluster (e.g., example.com)"
  type        = string
  nullable    = false

  validation {
    condition = can(regex(
      "^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,}$",
      lower(trimspace(var.domain))
    ))
    error_message = "domain must be a valid DNS domain name"
  }
}

variable "acme_email" {
  description = "Email address for ACME certificate registration"
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[^@]+@[^@]+\\.[^@]+$", trimspace(var.acme_email)))
    error_message = "acme_email must be a valid email address"
  }
}

variable "flux_namespace" {
  description = "Namespace where Flux controllers are installed"
  type        = string
  default     = "flux-system"
  nullable    = false

  validation {
    condition = (
      length(trimspace(var.flux_namespace)) > 0 &&
      length(trimspace(var.flux_namespace)) <= 63 &&
      can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", trimspace(var.flux_namespace)))
    )
    error_message = "flux_namespace must be a valid Kubernetes namespace name"
  }
}

# -----------------------------------------------------------------------------
# Feature Flags
# -----------------------------------------------------------------------------

variable "traefik_enabled" {
  description = "Enable the Traefik ingress controller"
  type        = bool
  default     = true
  nullable    = false
}

variable "cert_manager_enabled" {
  description = "Enable cert-manager for TLS certificate management"
  type        = bool
  default     = true
  nullable    = false
}

variable "external_dns_enabled" {
  description = "Enable ExternalDNS for automatic DNS record management"
  type        = bool
  default     = true
  nullable    = false
}

variable "vault_eso_enabled" {
  description = "Enable Vault + External Secrets Operator integration"
  type        = bool
  default     = true
  nullable    = false
}

variable "cnpg_enabled" {
  description = "Enable CloudNativePG for PostgreSQL databases"
  type        = bool
  default     = true
  nullable    = false
}

# Note: Valkey support is temporarily disabled due to provider version
# incompatibility. The valkey module requires helm ~> 3.1.1 and kubernetes
# ~> 3.0.1, while other modules use ~> 2.13.0 and ~> 2.25.0. This variable
# is retained for future compatibility when provider versions are unified.
# tflint-ignore: terraform_unused_declarations
variable "valkey_enabled" {
  description = "Enable Valkey for Redis-compatible caching (currently unsupported)"
  type        = bool
  default     = false
  nullable    = false

  validation {
    condition     = var.valkey_enabled == false
    error_message = "Valkey is not currently supported due to provider version incompatibility"
  }
}

# -----------------------------------------------------------------------------
# Cloudflare Configuration
# -----------------------------------------------------------------------------

variable "cloudflare_api_token_secret_name" {
  description = "Name of the Kubernetes secret containing the Cloudflare API token"
  type        = string

  validation {
    condition = (
      length(trimspace(var.cloudflare_api_token_secret_name)) > 0 &&
      length(trimspace(var.cloudflare_api_token_secret_name)) <= 253 &&
      can(regex("^[a-z0-9]([-.a-z0-9]*[a-z0-9])?$", trimspace(var.cloudflare_api_token_secret_name)))
    )
    error_message = "cloudflare_api_token_secret_name must be a valid Kubernetes Secret name"
  }
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for DNS management (optional, enables zone ID filter)"
  type        = string
  default     = null

  validation {
    condition = (
      var.cloudflare_zone_id == null ||
      can(regex("^[a-f0-9]{32}$", lower(trimspace(var.cloudflare_zone_id))))
    )
    error_message = "cloudflare_zone_id must be a 32-character hexadecimal string"
  }
}

# -----------------------------------------------------------------------------
# Vault Configuration
# -----------------------------------------------------------------------------

variable "vault_address" {
  description = "HTTPS endpoint of the external Vault appliance"
  type        = string
  default     = null

  validation {
    condition = (
      var.vault_address == null ||
      can(regex("^https://", trimspace(var.vault_address)))
    )
    error_message = "vault_address must be an HTTPS URL"
  }
}

variable "vault_ca_bundle_pem" {
  description = "PEM-encoded CA certificate for Vault TLS verification"
  type        = string
  default     = null
  sensitive   = true
}

variable "vault_approle_role_id" {
  description = "AppRole role_id for Vault authentication"
  type        = string
  default     = null
  sensitive   = true
}

variable "vault_approle_secret_id" {
  description = "AppRole secret_id for Vault authentication"
  type        = string
  default     = null
  sensitive   = true
}

variable "vault_kv_mount_path" {
  description = "KV v2 mount path in Vault for secret storage"
  type        = string
  default     = "secret"
  nullable    = false

  validation {
    condition = (
      length(trimspace(var.vault_kv_mount_path)) > 0 &&
      !startswith(trimspace(var.vault_kv_mount_path), "/") &&
      !endswith(trimspace(var.vault_kv_mount_path), "/") &&
      can(regex(
        "^[A-Za-z0-9][A-Za-z0-9/_-]*[A-Za-z0-9]$",
        trimspace(var.vault_kv_mount_path)
      ))
    )
    error_message = "vault_kv_mount_path must not have leading or trailing slashes and may contain letters, numbers, slashes, underscores, and hyphens"
  }
}

# -----------------------------------------------------------------------------
# cert-manager Configuration
# -----------------------------------------------------------------------------

variable "namecheap_api_secret_name" {
  description = "Name of the Kubernetes secret containing Namecheap API credentials"
  type        = string
  default     = "namecheap-api-credentials"

  validation {
    condition = (
      length(trimspace(var.namecheap_api_secret_name)) > 0 &&
      length(trimspace(var.namecheap_api_secret_name)) <= 253 &&
      can(regex("^[a-z0-9]([-.a-z0-9]*[a-z0-9])?$", trimspace(var.namecheap_api_secret_name)))
    )
    error_message = "namecheap_api_secret_name must be a valid Kubernetes Secret name"
  }
}

variable "cert_manager_vault_enabled" {
  description = "Enable Vault issuer in cert-manager"
  type        = bool
  default     = false
  nullable    = false
}

variable "cert_manager_vault_pki_path" {
  description = "Vault PKI signing path for cert-manager"
  type        = string
  default     = "pki/sign/nile-valley"
}

variable "cert_manager_webhook_enabled" {
  description = "Deploy the Namecheap webhook for DNS-01 challenges"
  type        = bool
  default     = false
  nullable    = false
}

# -----------------------------------------------------------------------------
# CNPG Configuration
# -----------------------------------------------------------------------------

variable "cnpg_cluster_name" {
  description = "Name of the CloudNativePG Cluster resource"
  type        = string
  default     = "nile-valley-pg-main"

  validation {
    condition = (
      length(trimspace(var.cnpg_cluster_name)) > 0 &&
      length(trimspace(var.cnpg_cluster_name)) <= 63 &&
      can(regex(
        "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        trimspace(var.cnpg_cluster_name)
      ))
    )
    error_message = "cnpg_cluster_name must be a valid Kubernetes resource name of 63 characters or fewer"
  }
}

variable "cnpg_instances" {
  description = "Number of PostgreSQL instances in the CNPG cluster"
  type        = number
  default     = 3

  validation {
    condition = (
      var.cnpg_instances >= 1 &&
      var.cnpg_instances <= 10 &&
      floor(var.cnpg_instances) == var.cnpg_instances
    )
    error_message = "cnpg_instances must be an integer between 1 and 10"
  }
}

variable "cnpg_storage_size" {
  description = "PVC storage size for each CNPG instance"
  type        = string
  default     = "50Gi"

  validation {
    condition = can(regex(
      "^[0-9]+(\\.[0-9]+)?[KMGTkmgt]i?$",
      trimspace(var.cnpg_storage_size)
    ))
    error_message = "cnpg_storage_size must be a valid Kubernetes quantity using K/M/G/T with optional i (e.g., 500M, 50Gi, 1Ti, 0.5G)"
  }
}

variable "cnpg_database_name" {
  description = "Initial database name for CNPG (PostgreSQL identifier)"
  type        = string
  default     = "nile_valley"

  validation {
    condition = (
      length(trimspace(var.cnpg_database_name)) > 0 &&
      length(trimspace(var.cnpg_database_name)) <= 63 &&
      can(regex(
        "^[a-zA-Z_][a-zA-Z0-9_]*$",
        trimspace(var.cnpg_database_name)
      ))
    )
    error_message = "cnpg_database_name must be a valid PostgreSQL identifier of 63 characters or fewer"
  }
}

variable "cnpg_database_owner" {
  description = "Owner of the initial CNPG database (PostgreSQL identifier)"
  type        = string
  default     = "nile_valley_app"

  validation {
    condition = (
      length(trimspace(var.cnpg_database_owner)) > 0 &&
      length(trimspace(var.cnpg_database_owner)) <= 63 &&
      can(regex(
        "^[a-zA-Z_][a-zA-Z0-9_]*$",
        trimspace(var.cnpg_database_owner)
      ))
    )
    error_message = "cnpg_database_owner must be a valid PostgreSQL identifier of 63 characters or fewer"
  }
}

variable "cnpg_backup_enabled" {
  description = "Enable S3-compatible backups for CNPG"
  type        = bool
  default     = false
  nullable    = false
}

variable "cnpg_backup_destination_path" {
  description = "S3 bucket path for CNPG backups (required when cnpg_backup_enabled is true)"
  type        = string
  default     = ""
}

variable "cnpg_backup_endpoint_url" {
  description = "S3-compatible endpoint URL for CNPG backups (required when cnpg_backup_enabled is true)"
  type        = string
  default     = ""
}

variable "cnpg_backup_s3_access_key_id" {
  description = "S3 access key ID for CNPG backups (required when cnpg_backup_enabled is true)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cnpg_backup_s3_secret_access_key" {
  description = "S3 secret access key for CNPG backups (required when cnpg_backup_enabled is true)"
  type        = string
  default     = ""
  sensitive   = true
}

# Note: Valkey configuration variables have been removed because valkey
# support is temporarily disabled. See the valkey_enabled variable comment.

# -----------------------------------------------------------------------------
# External Secrets Configuration (shared across modules)
# -----------------------------------------------------------------------------

variable "eso_cluster_secret_store_name" {
  description = "Name of the ClusterSecretStore for External Secrets Operator"
  type        = string
  default     = "vault-kv"

  validation {
    condition = (
      length(trimspace(var.eso_cluster_secret_store_name)) > 0 &&
      length(trimspace(var.eso_cluster_secret_store_name)) <= 63 &&
      can(regex(
        "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        trimspace(var.eso_cluster_secret_store_name)
      ))
    )
    error_message = "eso_cluster_secret_store_name must be a valid Kubernetes resource name of 63 characters or fewer"
  }
}

variable "cnpg_superuser_vault_path" {
  description = "Vault path for CNPG superuser credentials"
  type        = string
  default     = ""

  validation {
    condition = (
      !var.cnpg_enabled ||
      !var.vault_eso_enabled ||
      length(trimspace(var.cnpg_superuser_vault_path)) > 0
    )
    error_message = "cnpg_superuser_vault_path must be set when cnpg_enabled and vault_eso_enabled are true"
  }
}

variable "cnpg_app_vault_path" {
  description = "Vault path for CNPG application credentials"
  type        = string
  default     = ""

  validation {
    condition = (
      !var.cnpg_enabled ||
      !var.vault_eso_enabled ||
      length(trimspace(var.cnpg_app_vault_path)) > 0
    )
    error_message = "cnpg_app_vault_path must be set when cnpg_enabled and vault_eso_enabled are true"
  }
}
