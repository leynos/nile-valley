# Vault appliance module

Provision a hardened HashiCorp Vault appliance on DigitalOcean. The module
builds a dedicated droplet (or HA pair), attaches encrypted block storage,
wraps the nodes behind a managed load balancer, and generates a private
certificate authority plus recovery key material ready for bootstrap automation.

Requires [OpenTofu](https://opentofu.org/docs/intro/install/) 1.6 or later.
OpenTofu uses the Terraform configuration language, so the module examples
retain the standard `terraform` block syntax.

## Quick start

1. A DigitalOcean API token must be exported for the provider:

   ```sh
   export DIGITALOCEAN_TOKEN="<DIGITALOCEAN_TOKEN>"
   ```

2. The following configuration initializes the provider and calls the module,
   surfacing the key outputs:

   ```hcl
   terraform {
     required_version = ">= 1.6.0"

     required_providers {
       digitalocean = {
         source  = "opentofu/digitalocean"
         version = "~> 2.66"
       }
       tls = {
         source  = "hashicorp/tls"
         version = "~> 4.0"
       }
       random = {
         source  = "hashicorp/random"
         version = "~> 3.6"
       }
     }
   }

   provider "digitalocean" {}

   module "vault_appliance" {
     source = "git::https://github.com/OWNER/nile-valley.git//infra/modules/vault_appliance?ref=<TAG_OR_SHA>"

     name                     = "vault-appliance"
     region                   = "nyc1"
     certificate_common_name  = "vault.example.test"
     certificate_dns_names    = ["vault.example.test"]
     allowed_ssh_cidrs        = ["203.0.113.5/32"]
     tags                     = ["env:dev", "service:vault"]
     ha_enabled               = true
   }

   output "public_endpoint" {
     value = module.vault_appliance.public_endpoint
   }

   output "ca_certificate" {
     value = module.vault_appliance.ca_certificate
   }

   output "recovery_keys" {
     value     = module.vault_appliance.recovery_keys
     sensitive = true
   }
   ```

   The placeholder `OWNER` must be set to the GitHub organisation or account
   name. Pin `ref=<TAG_OR_SHA>` to a released tag or commit for reproducibility.

3. Initialize, plan, and apply the workspace:

   ```sh
   tofu init
   tofu plan
   tofu apply
   ```

4. Retrieve the bootstrap artefacts with:

   Private key files must be handled ephemerally on a secure machine. Move them
   immediately to encrypted secret storage with restricted access, delete local
   copies, and store recovery keys in the same encrypted secret store.

   ```sh
   tofu output public_endpoint
   tofu output -raw ca_certificate > vault-ca.pem
   tofu output -raw server_private_key > vault-server-key.pem
   tofu output -json recovery_keys | jq -r '.[]'
   ```

   The generated CA and server key pair are required by the bootstrap helper to
   configure Vault's listener and to register the TLS bundle on the load
   balancer.

## Outputs

- `public_endpoint` – name/IP tuple served by the load balancer on port 443.
- `ca_certificate` – PEM encoded CA bundle signing the Vault server certificate.
- `server_certificate` / `server_private_key` – PEM artefacts installed on both
  the droplet and the load balancer.
- `recovery_keys` / `recovery_threshold` – Shamir shares for the recovery seal.
- `droplet_ids`, `droplet_ipv4_addresses`, and `load_balancer_id` – identifiers
  for downstream automation.

## Operational notes

- SSH ingress defaults to closed. Explicit CIDR ranges should be supplied via
  `allowed_ssh_cidrs` when break-glass access is required by an operator.
- Set `ha_enabled = true` to provision an HA pair. The module automatically
  expands the block storage, firewall rules, and recovery key generation to
  match the replica count.
- Assign resources to a DigitalOcean project by passing `project_id`.
- Rotate generated certificates by tainting `tls_locally_signed_cert.server`
  and reapplying. The module automatically refreshes the managed load balancer
  certificate bundle.
- The module publishes recovery material and TLS private keys as sensitive
  outputs. A remote state backend with encryption at rest and strict access
  controls should secure the module state.
