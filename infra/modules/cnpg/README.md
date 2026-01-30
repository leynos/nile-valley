# CloudNativePG module

This module deploys [CloudNativePG](https://cloudnative-pg.io/) (CNPG) operator
and a PostgreSQL cluster with high availability, automatic failover, and
S3-compatible backups. It includes PostGIS support for geospatial workloads and
integrates with the `vault_eso` module for credential management via External
Secrets Operator (ESO).

## Overview

The module provisions:

- CloudNativePG operator via Helm
- A PostgreSQL cluster with configurable instances (primary + replicas)
- Optional S3-compatible backups to DigitalOcean Spaces or similar
- Optional ESO integration for secure credential management
- PodDisruptionBudget for cluster stability

## Prerequisites

- A Kubernetes cluster with cluster-admin access
- OpenTofu >= 1.6.0
- `conftest` (policy tests): requires conftest built with Open Policy Agent
  (OPA) >= 0.59.0 (Rego v1 syntax)
- (Optional) `vault_eso` module deployed for ESO-managed credentials
- (Optional) S3-compatible storage for backups (e.g., DigitalOcean Spaces)

## Usage

### Render mode (GitOps)

```hcl
module "cnpg" {
  source = "../cnpg"

  mode = "render"

  cluster_name     = "nile-valley-pg-main"
  database_name    = "nile_valley_prod"
  database_owner   = "nile_valley_user"
  instances        = 3
  postgis_enabled  = true
}

output "rendered_manifests" {
  value     = module.cnpg.rendered_manifests
  sensitive = true
}
```

### Apply mode (direct)

```hcl
provider "kubernetes" {
  config_path = var.kubeconfig_path
}

provider "helm" {
  kubernetes {
    config_path = var.kubeconfig_path
  }
}

module "cnpg" {
  source = "../cnpg"

  mode = "apply"

  cluster_name     = "nile-valley-pg-main"
  database_name    = "nile_valley_prod"
  database_owner   = "nile_valley_user"
  instances        = 3
  postgis_enabled  = true
}
```

### With ESO credentials

```hcl
module "cnpg" {
  source = "../cnpg"

  mode = "render"

  cluster_name   = "nile-valley-pg-main"
  database_name  = "nile_valley_prod"
  database_owner = "nile_valley_user"

  # ESO integration
  eso_enabled                       = true
  eso_cluster_secret_store_name     = "vault-kv"
  superuser_credentials_vault_path  = "databases/cnpg/superuser"
  app_credentials_vault_path        = "databases/cnpg/app"
}
```

### With S3 backups

```hcl
module "cnpg" {
  source = "../cnpg"

  mode = "render"

  cluster_name   = "nile-valley-pg-main"
  database_name  = "nile_valley_prod"
  database_owner = "nile_valley_user"

  # S3 backups
  backup_enabled          = true
  backup_destination_path = "s3://my-bucket/cnpg-backups/"
  backup_endpoint_url     = "https://nyc3.digitaloceanspaces.com"
  backup_schedule         = "0 0 * * *"
  backup_retention_policy = "30d"
}
```

## Inputs

### Core configuration

| Name                            | Description                                                             | Type           | Default                                     | Required |
| ------------------------------- | ----------------------------------------------------------------------- | -------------- | ------------------------------------------- | :------: |
| `mode`                          | Whether to render Flux manifests (`render`) or apply directly (`apply`) | `string`       | `"render"`                                  | no       |
| `operator_namespace`            | Namespace for CloudNativePG operator                                    | `string`       | `"cnpg-system"`                             | no       |
| `cluster_namespace`             | Namespace for the PostgreSQL cluster                                    | `string`       | `"databases"`                               | no       |
| `create_namespaces`             | Whether to create operator and cluster namespaces                       | `bool`         | `true`                                      | no       |
| `helm_release_name`             | Name for the operator Helm release                                      | `string`       | `"cloudnative-pg"`                          | no       |
| `chart_repository`              | Helm repository URL                                                     | `string`       | `"https://cloudnative-pg.github.io/charts"` | no       |
| `chart_name`                    | Helm chart name                                                         | `string`       | `"cloudnative-pg"`                          | no       |
| `chart_version`                 | Helm chart version                                                      | `string`       | `"0.26.1"`                                  | no       |
| `helm_wait`                     | Wait for Helm release to succeed                                        | `bool`         | `true`                                      | no       |
| `helm_timeout`                  | Helm operation timeout (seconds)                                        | `number`       | `600`                                       | no       |
| `helm_values`                   | Inline YAML values for Helm                                             | `list(string)` | `[]`                                        | no       |
| `flux_namespace`                | Flux controllers namespace (render mode)                                | `string`       | `"flux-system"`                             | no       |
| `flux_helm_repository_name`     | Flux HelmRepository name                                                | `string`       | `"cloudnative-pg"`                          | no       |
| `flux_helm_repository_interval` | HelmRepository reconciliation interval                                  | `string`       | `"24h"`                                     | no       |
| `flux_helm_release_interval`    | HelmRelease reconciliation interval                                     | `string`       | `"1h"`                                      | no       |

### Cluster configuration

| Name                      | Description                                      | Type          | Default                                   | Required |
| ------------------------- | ------------------------------------------------ | ------------- | ----------------------------------------- | :------: |
| `cluster_name`            | CNPG Cluster resource name                       | `string`      | `"nile-valley-pg-main"`                   | no       |
| `instances`               | PostgreSQL instances (1 primary + N-1 replicas)  | `number`      | `3`                                       | no       |
| `image_name`              | PostgreSQL container image                       | `string`      | `"ghcr.io/cloudnative-pg/postgis:16-3.4"` | no       |
| `storage_size`            | PVC storage size per instance                    | `string`      | `"50Gi"`                                  | no       |
| `storage_class`           | Kubernetes StorageClass                          | `string`      | `"do-block-storage"`                      | no       |
| `database_name`           | Initial database name                            | `string`      | `"nile_valley_prod"`                      | no       |
| `database_owner`          | Database owner username                          | `string`      | `"nile_valley_user"`                      | no       |
| `postgis_enabled`         | Install PostGIS extensions                       | `bool`        | `true`                                    | no       |
| `primary_update_strategy` | Update strategy (`unsupervised` or `supervised`) | `string`      | `"unsupervised"`                          | no       |
| `primary_update_method`   | Update method (`switchover` or `restart`)        | `string`      | `"switchover"`                            | no       |
| `postgresql_parameters`   | Custom PostgreSQL parameters                     | `map(string)` | `{}`                                      | no       |
| `resource_requests`       | Pod resource requests                            | `object`      | `{cpu="100m", memory="256Mi"}`            | no       |
| `resource_limits`         | Pod resource limits                              | `object`      | `{cpu="2", memory="2Gi"}`                 | no       |
| `pdb_enabled`             | Create PodDisruptionBudget                       | `bool`        | `true`                                    | no       |
| `pdb_min_available`       | Minimum available pods                           | `number`      | `1`                                       | no       |
| `pdb_name`                | PDB resource name                                | `string`      | `"cnpg-cluster-pdb"`                      | no       |

### Backup configuration

| Name                                | Description                                | Type     | Default                 | Required |
| ----------------------------------- | ------------------------------------------ | -------- | ----------------------- | :------: |
| `backup_enabled`                    | Enable S3-compatible backups               | `bool`   | `false`                 | no       |
| `backup_destination_path`           | S3 bucket path (e.g., `s3://bucket/path/`) | `string` | `""`                    | no       |
| `backup_endpoint_url`               | S3-compatible endpoint URL                 | `string` | `""`                    | no       |
| `backup_retention_policy`           | Retention period (e.g., `30d`)             | `string` | `"30d"`                 | no       |
| `backup_schedule`                   | Cron schedule for backups                  | `string` | `"0 0 * * *"`           | no       |
| `backup_s3_credentials_secret_name` | Secret for S3 credentials                  | `string` | `"cnpg-s3-credentials"` | no       |
| `backup_s3_access_key_id`           | S3 access key (sensitive)                  | `string` | `""`                    | no       |
| `backup_s3_secret_access_key`       | S3 secret key (sensitive)                  | `string` | `""`                    | no       |
| `wal_compression`                   | WAL compression algorithm                  | `string` | `"gzip"`                | no       |
| `scheduled_backup_name`             | Scheduled backup resource name             | `string` | `"daily-backup"`        | no       |

### Credentials configuration (ESO integration)

| Name                                | Description                                | Type     | Default                        | Required |
| ----------------------------------- | ------------------------------------------ | -------- | ------------------------------ | :------: |
| `eso_enabled`                       | Enable ESO for credential management       | `bool`   | `false`                        | no       |
| `eso_cluster_secret_store_name`     | ClusterSecretStore name (from `vault_eso`) | `string` | `"vault-kv"`                   | no       |
| `eso_refresh_interval`              | ExternalSecret refresh interval            | `string` | `"1h"`                         | no       |
| `superuser_credentials_vault_path`  | Vault KV path for superuser credentials    | `string` | `""`                           | no       |
| `superuser_credentials_secret_name` | Kubernetes Secret for superuser            | `string` | `"cnpg-superuser-credentials"` | no       |
| `app_credentials_vault_path`        | Vault KV path for app credentials          | `string` | `""`                           | no       |
| `app_credentials_secret_name`       | Kubernetes Secret for app                  | `string` | `"cnpg-app-credentials"`       | no       |
| `backup_credentials_vault_path`     | Vault KV path for S3 backup credentials    | `string` | `""`                           | no       |

See `variables-*.tf` files for the complete list of inputs with validation
rules.

## Outputs

| Name                                | Description                                  |
| ----------------------------------- | -------------------------------------------- |
| `operator_namespace`                | Namespace where CNPG operator is installed   |
| `cluster_namespace`                 | Namespace where PostgreSQL cluster runs      |
| `cluster_name`                      | CNPG Cluster resource name                   |
| `helm_release_name`                 | Operator Helm release name                   |
| `primary_service_name`              | Kubernetes service for primary instance      |
| `replica_service_name`              | Kubernetes service for replicas              |
| `primary_endpoint`                  | Fully qualified DNS endpoint for primary     |
| `replica_endpoint`                  | Fully qualified DNS endpoint for replicas    |
| `database_name`                     | Initial database name                        |
| `database_owner`                    | Database owner username                      |
| `superuser_credentials_secret_name` | Secret containing superuser credentials      |
| `app_credentials_secret_name`       | Secret containing app credentials            |
| `backup_enabled`                    | Whether backups are enabled                  |
| `sync_policy_contract`              | Contract for downstream workload consumption |
| `rendered_manifests`                | GitOps manifests (render mode only)          |

## Sync policy contract

The `sync_policy_contract` output provides a stable interface for downstream
workloads:

```hcl
{
  cluster = {
    name      = "nile-valley-pg-main"
    namespace = "databases"
  }
  endpoints = {
    primary = {
      host = "nile-valley-pg-main-rw.databases.svc.cluster.local"
      port = 5432
    }
    replica = {
      host = "nile-valley-pg-main-ro.databases.svc.cluster.local"
      port = 5432
    }
  }
  database = {
    name  = "nile_valley_prod"
    owner = "nile_valley_user"
  }
  credentials = {
    superuser_secret = {
      name      = "cnpg-superuser-credentials"
      namespace = "databases"
    }
    app_secret = {
      name      = "cnpg-app-credentials"
      namespace = "databases"
    }
  }
  backup = {
    enabled          = true
    destination_path = "s3://bucket/backups/"
    schedule         = "0 0 * * *"
  }
  postgis_enabled = true
}
```

Applications reference this contract to obtain connection details and
credential secret names without coupling to the module's internal
implementation.

## Integration with vault_eso module

When `eso_enabled = true`, the module creates ExternalSecret resources that
synchronize credentials from Vault:

```hcl
module "vault_eso" {
  source = "../vault_eso"
  # ... vault_eso configuration
}

module "cnpg" {
  source = "../cnpg"

  eso_enabled                   = true
  eso_cluster_secret_store_name = module.vault_eso.cluster_secret_store_kv_name

  superuser_credentials_vault_path = "databases/cnpg/superuser"
  app_credentials_vault_path       = "databases/cnpg/app"
}
```

The Vault secrets should contain `username` and `password` keys.

## Resources created

When `mode = "apply"`, the module creates:

1. **kubernetes_namespace.operator** – Operator namespace (optional)
2. **kubernetes_namespace.cluster** – Cluster namespace (optional)
3. **helm_release.cnpg_operator** – CloudNativePG operator
4. **kubernetes_manifest.cluster** – CNPG Cluster resource
5. **kubernetes_manifest.scheduled_backup** – ScheduledBackup (if enabled)
6. **kubernetes_manifest.s3_credentials_secret** – S3 credentials (if backups
   enabled with inline credentials)
7. **kubernetes_manifest.superuser_external_secret** – ESO ExternalSecret
   (if ESO enabled)
8. **kubernetes_manifest.app_external_secret** – ESO ExternalSecret
   (if ESO enabled)
9. **kubernetes_manifest.pdb** – PodDisruptionBudget (if enabled)

## Design decisions

See
[docs/execplans/infra-phase-2-cloud-native-pg-module.md](../../../docs/execplans/infra-phase-2-cloud-native-pg-module.md)
 for detailed design decisions and rationale.
