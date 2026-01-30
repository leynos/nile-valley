# OpenTofu State Backend Configuration

This document describes the state management strategy for OpenTofu
configurations in the Nile Valley infrastructure.

## Overview

OpenTofu state is stored in DigitalOcean Spaces, an Amazon Simple Storage
Service (S3)-compatible object storage service. This provides:

- **Persistence**: State survives beyond individual continuous integration (CI)
  runs.
- **Consistency**: Multiple runs converge on the same state.
- **Versioning**: Object versioning enables state recovery.
- **Isolation**: Workspaces separate state for different clusters.

## Backend Configuration

The backend is configured in `infra/backend-config/spaces.tfbackend`:

    bucket                      = "nile-valley-tofu-state"
    region                      = "nyc3"
    endpoint                    = "nyc3.digitaloceanspaces.com"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    use_path_style              = true

Sensitive values (access key, secret key, and state key) are passed at runtime
to avoid storing credentials in version control.

## Initialization

To initialize a configuration with the Spaces backend:

    export SPACES_ACCESS_KEY="example-access-key"
    export SPACES_SECRET_KEY="example-secret-key"
    export CLUSTER_NAME="preview-123"

    tofu init \
      -backend-config=../../backend-config/spaces.tfbackend \
      -backend-config="access_key=$SPACES_ACCESS_KEY" \
      -backend-config="secret_key=$SPACES_SECRET_KEY" \
      -backend-config="key=clusters/${CLUSTER_NAME}/terraform.tfstate"

## Workspace Isolation

Each cluster uses a separate state file, isolated by the `key` parameter:

- `clusters/preview-123/terraform.tfstate`
- `clusters/staging/terraform.tfstate`
- `clusters/production/terraform.tfstate`

This prevents state conflicts between clusters while using a single Spaces
bucket.

## Credential Management

Spaces credentials are stored in HashiCorp Vault and retrieved by the
`nile-valley-infra-k8s` action during execution. The credentials require:

- **Read/Write access** to the `nile-valley-tofu-state` bucket.
- **List access** for workspace enumeration.

Never commit Spaces credentials to version control. The action retrieves them
from Vault using the AppRole authentication method.

## State Locking

DigitalOcean Spaces does not natively support DynamoDB-style state locking.
To prevent concurrent modifications:

1. The action should run serially per cluster (enforced by GitHub Actions
   concurrency groups).
2. Future iterations may add a lock table using an external service.

## Recovery Procedures

### State Corruption

If state becomes corrupted:

1. Enable object versioning on the Spaces bucket (if not already enabled).
2. List object versions: `s3cmd ls --versions s3://nile-valley-tofu-state/`.
3. Restore the previous version of the state file.
4. Run `tofu refresh` to reconcile.

### Lost State

If state is completely lost:

1. List existing resources via the DigitalOcean API or console.
2. Create a minimal configuration matching the existing resources.
3. Use `tofu import` to re-associate resources with state.
4. Run `tofu plan` to verify no unexpected changes.

### State Migration

To migrate state between backends:

1. Initialize with the old backend: `tofu init`.
2. Create a state backup: `tofu state pull > backup.tfstate`.
3. Reinitialize with the new backend: `tofu init -migrate-state`.
4. Verify the migration: `tofu plan`.

## Security Considerations

- **Encryption at rest**: Spaces encrypts objects by default.
- **Encryption in transit**: All API calls use HTTPS.
- **Access control**: Spaces access keys are scoped to the specific bucket.
- **Audit logging**: Enable Spaces access logging for compliance.

State files may contain sensitive outputs (e.g., kubeconfig). Ensure the bucket
is not publicly accessible and access keys are rotated regularly.
