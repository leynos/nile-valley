# Platform Render Orchestration Module
#
# Wires all platform modules together in render mode, producing a unified set
# of Flux-ready manifests for GitOps workflows. Each module is conditionally
# invoked based on feature flags.
#
# The module merges all `rendered_manifests` outputs into a single map and
# validates that there are no path collisions between modules.

locals {
  # Normalise inputs
  cluster_name = trimspace(var.cluster_name)
  domain       = lower(trimspace(var.domain))
  acme_email   = trimspace(var.acme_email)
  vault_ca_bundle_pem = trimspace(
    var.vault_ca_bundle_pem != null ? var.vault_ca_bundle_pem : ""
  )
  vault_approle_role_id = trimspace(
    var.vault_approle_role_id != null ? var.vault_approle_role_id : ""
  )
  vault_approle_secret_id = trimspace(
    var.vault_approle_secret_id != null ? var.vault_approle_secret_id : ""
  )

  # External DNS TXT owner ID (unique per cluster)
  txt_owner_id = local.cluster_name

  # Zone ID filter for ExternalDNS (if provided)
  zone_id_filter = (
    var.cloudflare_zone_id != null
    ? { (local.domain) = var.cloudflare_zone_id }
    : {}
  )
}

# -----------------------------------------------------------------------------
# Traefik Ingress Controller
# -----------------------------------------------------------------------------

module "traefik" {
  count  = var.traefik_enabled ? 1 : 0
  source = "../traefik"

  mode = "render"

  acme_email                       = local.acme_email
  cloudflare_api_token_secret_name = var.cloudflare_api_token_secret_name
  flux_namespace                   = var.flux_namespace
}

# -----------------------------------------------------------------------------
# cert-manager Certificate Management
# -----------------------------------------------------------------------------

module "cert_manager" {
  count  = var.cert_manager_enabled ? 1 : 0
  source = "../cert_manager"

  mode = "render"

  acme_email                = local.acme_email
  namecheap_api_secret_name = var.namecheap_api_secret_name
  flux_namespace            = var.flux_namespace

  # Vault issuer configuration
  vault_enabled           = var.cert_manager_vault_enabled
  vault_server            = var.vault_address
  vault_pki_path          = var.cert_manager_vault_pki_path
  vault_token_secret_name = "vault-token"
  vault_ca_bundle_pem     = local.vault_ca_bundle_pem

  # Namecheap webhook configuration
  webhook_release_enabled = var.cert_manager_webhook_enabled
}

# -----------------------------------------------------------------------------
# ExternalDNS Automatic DNS Management
# -----------------------------------------------------------------------------

module "external_dns" {
  count  = var.external_dns_enabled ? 1 : 0
  source = "../external_dns"

  mode = "render"

  domain_filters                   = [local.domain]
  txt_owner_id                     = local.txt_owner_id
  cloudflare_api_token_secret_name = var.cloudflare_api_token_secret_name
  zone_id_filter                   = local.zone_id_filter
  flux_namespace                   = var.flux_namespace
}

# -----------------------------------------------------------------------------
# Vault + External Secrets Operator
# -----------------------------------------------------------------------------

module "vault_eso" {
  count  = var.vault_eso_enabled ? 1 : 0
  source = "../vault_eso"

  mode = "render"

  vault_address       = coalesce(var.vault_address, "https://vault.example.test:8200")
  vault_ca_bundle_pem = local.vault_ca_bundle_pem
  approle_role_id     = local.vault_approle_role_id
  approle_secret_id   = local.vault_approle_secret_id
  kv_mount_path       = var.vault_kv_mount_path

  cluster_secret_store_kv_name = var.eso_cluster_secret_store_name
  flux_namespace               = var.flux_namespace
}

# -----------------------------------------------------------------------------
# CloudNativePG PostgreSQL
# -----------------------------------------------------------------------------

module "cnpg" {
  count  = var.cnpg_enabled ? 1 : 0
  source = "../cnpg"

  mode = "render"

  cluster_name    = var.cnpg_cluster_name
  instances       = var.cnpg_instances
  storage_size    = var.cnpg_storage_size
  database_name   = var.cnpg_database_name
  database_owner  = var.cnpg_database_owner
  flux_namespace  = var.flux_namespace

  # Backup configuration
  backup_enabled              = var.cnpg_backup_enabled
  backup_destination_path     = var.cnpg_backup_destination_path
  backup_endpoint_url         = var.cnpg_backup_endpoint_url
  backup_s3_access_key_id     = var.cnpg_backup_s3_access_key_id
  backup_s3_secret_access_key = var.cnpg_backup_s3_secret_access_key

  # ESO integration
  eso_enabled                      = var.vault_eso_enabled
  eso_cluster_secret_store_name    = var.eso_cluster_secret_store_name
  superuser_credentials_vault_path = var.cnpg_superuser_vault_path
  app_credentials_vault_path       = var.cnpg_app_vault_path
}

# -----------------------------------------------------------------------------
# Valkey Redis-compatible Cache
# -----------------------------------------------------------------------------
# Note: Valkey is temporarily excluded from platform_render due to provider
# version incompatibility. The valkey module requires helm ~> 3.1.1 and
# kubernetes ~> 3.0.1, while other modules use ~> 2.13.0 and ~> 2.25.0.
# A future upgrade will unify provider versions across all modules, at which
# point valkey can be re-added to this orchestration module.
# See: docs/execplans/infra-3-1-1-develop-the-nile-valley-infra-k8s-action.md

# -----------------------------------------------------------------------------
# Manifest Aggregation and Validation
# -----------------------------------------------------------------------------

locals {
  # Collect rendered manifests from each enabled module
  traefik_manifests      = var.traefik_enabled ? module.traefik[0].rendered_manifests : {}
  cert_manager_manifests = var.cert_manager_enabled ? module.cert_manager[0].rendered_manifests : {}
  external_dns_manifests = var.external_dns_enabled ? module.external_dns[0].rendered_manifests : {}
  vault_eso_manifests    = var.vault_eso_enabled ? module.vault_eso[0].rendered_manifests : {}
  cnpg_manifests         = var.cnpg_enabled ? module.cnpg[0].rendered_manifests : {}

  # Merge all manifests into a single map
  all_manifests = merge(
    local.traefik_manifests,
    local.cert_manager_manifests,
    local.external_dns_manifests,
    local.vault_eso_manifests,
    local.cnpg_manifests,
  )

  # Count manifests per module for validation
  manifest_counts = {
    traefik      = length(local.traefik_manifests)
    cert_manager = length(local.cert_manager_manifests)
    external_dns = length(local.external_dns_manifests)
    vault_eso    = length(local.vault_eso_manifests)
    cnpg         = length(local.cnpg_manifests)
  }

  # Total expected count (sum of individual counts)
  expected_total = sum(values(local.manifest_counts))

  # Actual count after merge (detects collisions)
  actual_total = length(local.all_manifests)

  # Path collision detection
  has_path_collisions = local.actual_total < local.expected_total
}

output "cnpg_backup_configuration_valid" {
  description = "Validate CNPG backup inputs when backups are enabled."
  value       = true
  precondition {
    condition = !var.cnpg_backup_enabled || (
      length(trimspace(var.cnpg_backup_destination_path)) > 0 &&
      length(trimspace(var.cnpg_backup_endpoint_url)) > 0 &&
      length(trimspace(var.cnpg_backup_s3_access_key_id)) > 0 &&
      length(trimspace(var.cnpg_backup_s3_secret_access_key)) > 0
    )
    error_message = "CNPG backup configuration requires destination path, endpoint URL, and S3 credentials when cnpg_backup_enabled is true"
  }
}

output "manifests_have_no_path_collisions" {
  description = "Ensure merged manifests contain no duplicate paths."
  value       = true
  precondition {
    condition     = !local.has_path_collisions
    error_message = "Path collision detected: expected ${local.expected_total} manifests, got ${local.actual_total}. Check for duplicate paths across modules."
  }
}
