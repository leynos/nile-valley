locals {
  # HelmRepository for CloudNativePG chart
  flux_helm_repository_manifest = {
    apiVersion = "source.toolkit.fluxcd.io/v1"
    kind       = "HelmRepository"
    metadata = {
      name      = local.flux_helm_repository_name
      namespace = local.flux_namespace
      labels    = local.common_labels
    }
    spec = merge({
      interval = local.flux_helm_repository_interval
      url      = local.chart_repository
      }, startswith(local.chart_repository, "oci://") ? {
      type = "oci"
    } : {})
  }

  # Operator namespace
  operator_namespace_manifest = {
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name   = local.operator_namespace
      labels = local.common_labels
    }
  }

  # Cluster namespace
  cluster_namespace_manifest = {
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name   = local.cluster_namespace
      labels = local.common_labels
    }
  }

  # Operator HelmRelease
  flux_helmrelease_manifest = {
    apiVersion = "helm.toolkit.fluxcd.io/v2"
    kind       = "HelmRelease"
    metadata = {
      name      = local.helm_release_name
      namespace = local.operator_namespace
      labels    = local.common_labels
    }
    spec = {
      interval = local.flux_helm_release_interval
      install = {
        remediation = {
          retries = 3
        }
      }
      upgrade = {
        remediation = {
          retries              = 3
          remediateLastFailure = true
        }
      }
      chart = {
        spec = {
          chart = local.chart_name
          sourceRef = {
            kind      = "HelmRepository"
            name      = local.flux_helm_repository_name
            namespace = local.flux_namespace
          }
          version = local.chart_version
        }
      }
      values = local.merged_helm_values_map
    }
  }

  # CNPG Cluster resource
  cluster_manifest = {
    apiVersion = "postgresql.cnpg.io/v1"
    kind       = "Cluster"
    metadata = {
      name      = local.cluster_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    spec = merge(
      {
        instances             = local.instances
        imageName             = local.image_name
        primaryUpdateStrategy = local.primary_update_strategy
        primaryUpdateMethod   = local.primary_update_method
        enableSuperuserAccess = true

        storage = {
          size         = local.storage_size
          storageClass = local.storage_class
        }

        bootstrap = {
          initdb = merge(
            {
              database = local.database_name
              owner    = local.database_owner
            },
            length(local.postgis_sql) > 0 ? {
              postInitTemplateSQL = local.postgis_sql
            } : {}
          )
        }

        resources = {
          requests = {
            cpu    = var.resource_requests.cpu
            memory = var.resource_requests.memory
          }
          limits = {
            cpu    = var.resource_limits.cpu
            memory = var.resource_limits.memory
          }
        }
      },
      length(var.postgresql_parameters) > 0 ? {
        postgresql = {
          parameters = var.postgresql_parameters
        }
      } : {},
      local.eso_enabled ? {
        superuserSecret = {
          name = local.superuser_credentials_secret_name
        }
      } : {},
      local.backup_enabled ? {
        backup = {
          barmanObjectStore = {
            destinationPath = local.backup_destination_path
            endpointURL     = local.backup_endpoint_url
            s3Credentials = {
              accessKeyId = {
                name = local.backup_s3_credentials_secret_name
                key  = "ACCESS_KEY_ID"
              }
              secretAccessKey = {
                name = local.backup_s3_credentials_secret_name
                key  = "SECRET_ACCESS_KEY"
              }
            }
            wal = {
              compression = local.wal_compression
            }
          }
          retentionPolicy = local.backup_retention_policy
        }
      } : {}
    )
  }

  # ScheduledBackup resource (when backup is enabled)
  scheduled_backup_manifest = local.backup_enabled ? {
    apiVersion = "postgresql.cnpg.io/v1"
    kind       = "ScheduledBackup"
    metadata = {
      name      = local.scheduled_backup_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    spec = {
      schedule = local.backup_schedule
      cluster = {
        name = local.cluster_name
      }
      backupOwnerReference = "self"
    }
  } : null

  # S3 credentials Secret (when backup is enabled and inline credentials provided)
  s3_credentials_secret_manifest = (
    local.backup_enabled &&
    length(trimspace(var.backup_s3_access_key_id)) > 0 &&
    length(trimspace(var.backup_s3_secret_access_key)) > 0
    ) ? {
    apiVersion = "v1"
    kind       = "Secret"
    metadata = {
      name      = local.backup_s3_credentials_secret_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    type = "Opaque"
    stringData = {
      ACCESS_KEY_ID     = var.backup_s3_access_key_id
      SECRET_ACCESS_KEY = var.backup_s3_secret_access_key
    }
  } : null

  # PodDisruptionBudget for cluster
  pdb_manifest = local.pdb_enabled ? {
    apiVersion = "policy/v1"
    kind       = "PodDisruptionBudget"
    metadata = {
      name      = local.pdb_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    spec = {
      minAvailable = var.pdb_min_available
      selector = {
        matchLabels = {
          "cnpg.io/cluster" = local.cluster_name
        }
      }
    }
  } : null

  # ExternalSecret for superuser credentials (when ESO is enabled)
  superuser_external_secret_manifest = (
    local.eso_enabled &&
    length(local.superuser_credentials_vault_path) > 0
    ) ? {
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = local.superuser_credentials_secret_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    spec = {
      refreshInterval = local.eso_refresh_interval
      secretStoreRef = {
        name = local.eso_cluster_secret_store_name
        kind = "ClusterSecretStore"
      }
      target = {
        name           = local.superuser_credentials_secret_name
        creationPolicy = "Owner"
      }
      data = [
        {
          secretKey = "username"
          remoteRef = {
            key      = local.superuser_credentials_vault_path
            property = "username"
          }
        },
        {
          secretKey = "password"
          remoteRef = {
            key      = local.superuser_credentials_vault_path
            property = "password"
          }
        }
      ]
    }
  } : null

  # ExternalSecret for app credentials (when ESO is enabled)
  app_external_secret_manifest = (
    local.eso_enabled &&
    length(local.app_credentials_vault_path) > 0
    ) ? {
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = local.app_credentials_secret_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    spec = {
      refreshInterval = local.eso_refresh_interval
      secretStoreRef = {
        name = local.eso_cluster_secret_store_name
        kind = "ClusterSecretStore"
      }
      target = {
        name           = local.app_credentials_secret_name
        creationPolicy = "Owner"
      }
      data = [
        {
          secretKey = "username"
          remoteRef = {
            key      = local.app_credentials_vault_path
            property = "username"
          }
        },
        {
          secretKey = "password"
          remoteRef = {
            key      = local.app_credentials_vault_path
            property = "password"
          }
        }
      ]
    }
  } : null

  # ExternalSecret for backup credentials (when ESO is enabled and vault path provided)
  backup_external_secret_manifest = (
    local.eso_enabled &&
    local.backup_enabled &&
    length(local.backup_credentials_vault_path) > 0
    ) ? {
    apiVersion = "external-secrets.io/v1"
    kind       = "ExternalSecret"
    metadata = {
      name      = local.backup_s3_credentials_secret_name
      namespace = local.cluster_namespace
      labels    = local.cluster_labels
    }
    spec = {
      refreshInterval = local.eso_refresh_interval
      secretStoreRef = {
        name = local.eso_cluster_secret_store_name
        kind = "ClusterSecretStore"
      }
      target = {
        name           = local.backup_s3_credentials_secret_name
        creationPolicy = "Owner"
      }
      data = [
        {
          secretKey = "ACCESS_KEY_ID"
          remoteRef = {
            key      = local.backup_credentials_vault_path
            property = "access_key_id"
          }
        },
        {
          secretKey = "SECRET_ACCESS_KEY"
          remoteRef = {
            key      = local.backup_credentials_vault_path
            property = "secret_access_key"
          }
        }
      ]
    }
  } : null

  # Kustomization manifest
  kustomization_resources = concat(
    ["../sources/cloudnative-pg-repo.yaml"],
    ["namespace-cnpg-system.yaml", "namespace-databases.yaml"],
    ["cnpg-operator-helmrelease.yaml"],
    ["nile-valley-pg-cluster.yaml"],
    local.pdb_enabled ? ["pdb-cnpg-cluster.yaml"] : [],
    local.backup_enabled && local.scheduled_backup_manifest != null ? ["scheduled-backup.yaml"] : [],
    local.s3_credentials_secret_manifest != null ? ["s3-credentials-secret.yaml"] : [],
    local.superuser_external_secret_manifest != null ? ["external-secret-superuser.yaml"] : [],
    local.app_external_secret_manifest != null ? ["external-secret-app.yaml"] : [],
    local.backup_external_secret_manifest != null ? ["external-secret-backup.yaml"] : []
  )

  kustomization_manifest = {
    apiVersion = "kustomize.config.k8s.io/v1beta1"
    kind       = "Kustomization"
    resources  = local.kustomization_resources
  }

  # Rendered manifests map
  rendered_manifests = merge(
    {
      "platform/sources/cloudnative-pg-repo.yaml" = format(
        "%s\n",
        yamlencode(local.flux_helm_repository_manifest)
      )
      "platform/databases/namespace-cnpg-system.yaml" = format(
        "%s\n",
        yamlencode(local.operator_namespace_manifest)
      )
      "platform/databases/namespace-databases.yaml" = format(
        "%s\n",
        yamlencode(local.cluster_namespace_manifest)
      )
      "platform/databases/cnpg-operator-helmrelease.yaml" = format(
        "%s\n",
        yamlencode(local.flux_helmrelease_manifest)
      )
      "platform/databases/nile-valley-pg-cluster.yaml" = format(
        "%s\n",
        yamlencode(local.cluster_manifest)
      )
      "platform/databases/kustomization.yaml" = format(
        "%s\n",
        yamlencode(local.kustomization_manifest)
      )
    },
    local.pdb_enabled ? {
      "platform/databases/pdb-cnpg-cluster.yaml" = format(
        "%s\n",
        yamlencode(local.pdb_manifest)
      )
    } : {},
    local.scheduled_backup_manifest != null ? {
      "platform/databases/scheduled-backup.yaml" = format(
        "%s\n",
        yamlencode(local.scheduled_backup_manifest)
      )
    } : {},
    local.s3_credentials_secret_manifest != null ? {
      "platform/databases/s3-credentials-secret.yaml" = format(
        "%s\n",
        yamlencode(local.s3_credentials_secret_manifest)
      )
    } : {},
    local.superuser_external_secret_manifest != null ? {
      "platform/databases/external-secret-superuser.yaml" = format(
        "%s\n",
        yamlencode(local.superuser_external_secret_manifest)
      )
    } : {},
    local.app_external_secret_manifest != null ? {
      "platform/databases/external-secret-app.yaml" = format(
        "%s\n",
        yamlencode(local.app_external_secret_manifest)
      )
    } : {},
    local.backup_external_secret_manifest != null ? {
      "platform/databases/external-secret-backup.yaml" = format(
        "%s\n",
        yamlencode(local.backup_external_secret_manifest)
      )
    } : {}
  )
}
