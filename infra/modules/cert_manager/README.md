# Cert-manager module

Deploys [cert-manager](https://github.com/cert-manager/cert-manager) using Helm
and configures ClusterIssuers for Automated Certificate Management Environment
(ACME, Let's Encrypt) and Vault-based certificate issuance. Supports render
mode for Flux-ready manifests and apply mode for direct cluster provisioning.

## Prerequisites

- A Kubernetes cluster with cluster-admin access
- A Kubernetes Secret containing Namecheap API credentials (for ACME DNS-01)
- A Kubernetes Secret containing a Vault token and CA bundle material (when
  `vault_enabled` is true)
- OpenTofu >= 1.6.0
- `conftest` (policy tests): requires conftest built with OPA >= 0.59.0 (Rego
  v1 syntax)

## Usage

```hcl
module "cert_manager" {
  source = "path/to/modules/cert_manager"

  mode = "apply"

  acme_email               = "platform@example.test"
  namecheap_api_secret_name = "namecheap-api-credentials"

  vault_enabled          = true
  vault_server           = "https://vault.example.test:8200"
  vault_pki_path          = "pki/sign/example"
  vault_token_secret_name = "vault-token"
  vault_ca_bundle_pem      = file("${path.module}/vault-ca.pem")
}
```

### Render mode (Flux manifests)

When `mode = "render"`, the module returns a `rendered_manifests` map, keyed by
the intended GitOps path inside `nile-valley-infra`.

```hcl
module "cert_manager" {
  source = "path/to/modules/cert_manager"

  mode = "render"

  acme_email               = "platform@example.test"
  namecheap_api_secret_name = "namecheap-api-credentials"

  vault_enabled          = true
  vault_server           = "https://vault.example.test:8200"
  vault_pki_path          = "pki/sign/example"
  vault_token_secret_name = "vault-token"
  vault_ca_bundle_pem      = file("${path.module}/vault-ca.pem")
}

resource "local_file" "manifests" {
  for_each = module.cert_manager.rendered_manifests

  filename = "${path.module}/output/${each.key}"
  content  = each.value
}
```

## Inputs

| Name                                      | Description                                                                                | Type           | Default                                                    | Required |
| ----------------------------------------- | ------------------------------------------------------------------------------------------ | -------------- | ---------------------------------------------------------- | -------- |
| `mode`                                    | Whether to render Flux manifests (`render`) or apply resources directly (`apply`)          | `string`       | `"render"`                                                 | no       |
| `namespace`                               | Namespace where cert-manager will be installed                                             | `string`       | `"cert-manager"`                                           | no       |
| `create_namespace`                        | Whether the module should create the cert-manager namespace                                | `bool`         | `true`                                                     | no       |
| `helm_release_name`                       | Name assigned to the cert-manager Helm release                                             | `string`       | `"cert-manager"`                                           | no       |
| `chart_repository`                        | Helm repository hosting the cert-manager chart                                             | `string`       | `"oci://quay.io/jetstack/charts"`                          | no       |
| `chart_name`                              | Name of the Helm chart used to install cert-manager                                        | `string`       | `"cert-manager"`                                           | no       |
| `chart_version`                           | Exact Helm chart version for cert-manager                                                  | `string`       | `"v1.19.2"`                                                | no       |
| `helm_wait`                               | Whether to wait for the Helm release to report success                                     | `bool`         | `true`                                                     | no       |
| `helm_timeout`                            | Timeout (in seconds) for the Helm release operation                                        | `number`       | `600`                                                      | no       |
| `helm_values`                             | Inline YAML values passed to the cert-manager Helm release                                 | `list(string)` | `[]`                                                       | no       |
| `helm_values_files`                       | Additional YAML files providing values for cert-manager                                    | `list(string)` | `[]`                                                       | no       |
| `install_crds`                            | Whether to install cert-manager CRDs via Helm                                              | `bool`         | `true`                                                     | no       |
| `controller_replica_count`                | Replica count for the cert-manager controller                                              | `number`       | `3`                                                        | no       |
| `controller_resources`                    | Resource requests and limits for the cert-manager controller                               | `object`       | See module                                                 | no       |
| `webhook_replica_count`                   | Replica count for the cert-manager webhook                                                 | `number`       | `3`                                                        | no       |
| `webhook_resources`                       | Resource requests and limits for the cert-manager webhook                                  | `object`       | See module                                                 | no       |
| `cainjector_replica_count`                | Replica count for the cert-manager cainjector                                              | `number`       | `3`                                                        | no       |
| `cainjector_resources`                    | Resource requests and limits for the cert-manager cainjector                               | `object`       | See module                                                 | no       |
| `pdb_enabled`                             | Whether to render/apply PodDisruptionBudgets for cert-manager                              | `bool`         | `true`                                                     | no       |
| `pdb_min_available`                       | Minimum available pods for cert-manager webhook/cainjector PDBs                            | `number`       | `2`                                                        | no       |
| `webhook_pdb_name`                        | Name of the PodDisruptionBudget for cert-manager webhook                                   | `string`       | `"cert-manager-webhook-pdb"`                               | no       |
| `cainjector_pdb_name`                     | Name of the PodDisruptionBudget for cert-manager cainjector                                | `string`       | `"cert-manager-cainjector-pdb"`                            | no       |
| `flux_namespace`                          | Namespace where Flux controllers and sources run (render mode)                             | `string`       | `"flux-system"`                                            | no       |
| `flux_helm_repository_name`               | Flux HelmRepository name for the cert-manager chart                                        | `string`       | `"jetstack"`                                               | no       |
| `flux_helm_repository_interval`           | Interval for the Flux HelmRepository reconciliation                                        | `string`       | `"24h"`                                                    | no       |
| `flux_helm_release_interval`              | Interval for the Flux HelmRelease reconciliation                                           | `string`       | `"1h"`                                                     | no       |
| `acme_email`                              | Email address registered with the ACME certificate authority                               | `string`       | -                                                          | **yes**  |
| `acme_staging_enabled`                    | Whether to render the Let's Encrypt staging ClusterIssuer                                  | `bool`         | `true`                                                     | no       |
| `acme_production_enabled`                 | Whether to render the Let's Encrypt production ClusterIssuer                               | `bool`         | `true`                                                     | no       |
| `acme_staging_server`                     | ACME server URL for Let's Encrypt staging                                                  | `string`       | `"https://acme-staging-v02.api.letsencrypt.org/directory"` | no       |
| `acme_production_server`                  | ACME server URL for Let's Encrypt production                                               | `string`       | `"https://acme-v02.api.letsencrypt.org/directory"`         | no       |
| `acme_staging_issuer_name`                | Name of the ACME staging ClusterIssuer                                                     | `string`       | `"letsencrypt-staging"`                                    | no       |
| `acme_production_issuer_name`             | Name of the ACME production ClusterIssuer                                                  | `string`       | `"letsencrypt-production"`                                 | no       |
| `acme_staging_account_key_secret_name`    | Secret name storing the ACME staging account private key                                   | `string`       | `"letsencrypt-staging-account-key"`                        | no       |
| `acme_production_account_key_secret_name` | Secret name storing the ACME production account private key                                | `string`       | `"letsencrypt-production-account-key"`                     | no       |
| `webhook_group_name`                      | API group name used by the Namecheap DNS-01 webhook solver                                 | `string`       | `"acme.example.com"`                                       | no       |
| `webhook_solver_name`                     | Solver name registered by the Namecheap DNS-01 webhook                                     | `string`       | `"namecheap"`                                              | no       |
| `namecheap_api_secret_name`               | Secret containing Namecheap API credentials                                                | `string`       | -                                                          | **yes**  |
| `namecheap_api_key_key`                   | Key in the Namecheap secret containing the API key                                         | `string`       | `"api-key"`                                                | no       |
| `namecheap_api_user_key`                  | Key in the Namecheap secret containing the API user                                        | `string`       | `"api-user"`                                               | no       |
| `webhook_release_enabled`                 | Whether to deploy the Namecheap DNS-01 webhook Helm release                                | `bool`         | `false`                                                    | no       |
| `webhook_release_name`                    | Name assigned to the Namecheap webhook Helm release                                        | `string`       | `"cert-manager-webhook-namecheap"`                         | no       |
| `webhook_helm_repository_name`            | Flux HelmRepository name for the Namecheap webhook chart                                   | `string`       | `"private-helm-repo"`                                      | no       |
| `webhook_repository_interval`             | Interval for the Namecheap webhook HelmRepository reconciliation                           | `string`       | `"1h"`                                                     | no       |
| `webhook_chart_repository`                | Helm repository hosting the Namecheap webhook chart                                        | `string`       | `null`                                                     | no       |
| `webhook_chart_name`                      | Name of the Namecheap webhook chart                                                        | `string`       | `"cert-manager-webhook-namecheap"`                         | no       |
| `webhook_chart_version`                   | Chart version for the Namecheap webhook                                                    | `string`       | `"0.2.0"`                                                  | no       |
| `webhook_release_interval`                | Interval for the Namecheap webhook HelmRelease reconciliation                              | `string`       | `"1h"`                                                     | no       |
| `webhook_repository_type`                 | Optional repository type for the Namecheap webhook HelmRepository                          | `string`       | `null`                                                     | no       |
| `webhook_release_replica_count`           | Replica count for the Namecheap webhook                                                    | `number`       | `2`                                                        | no       |
| `vault_enabled`                           | Whether to render the Vault ClusterIssuer                                                  | `bool`         | `false`                                                    | no       |
| `vault_issuer_name`                       | Name of the Vault ClusterIssuer                                                            | `string`       | `"vault-issuer"`                                           | no       |
| `vault_server`                            | Vault server URL (must be https://). Required when `vault_enabled` is true.                | `string`       | `null`                                                     | no       |
| `vault_pki_path`                          | Vault PKI signing path (e.g., pki/sign/example). Required when `vault_enabled` is true.    | `string`       | `null`                                                     | no       |
| `vault_token_secret_name`                 | Secret containing the Vault token for cert-manager. Required when `vault_enabled` is true. | `string`       | `null`                                                     | no       |
| `vault_token_secret_key`                  | Key in the Vault token secret containing the token                                         | `string`       | `"token"`                                                  | no       |
| `vault_ca_bundle_pem`                     | PEM-encoded CA bundle for Vault TLS verification. Required when `vault_enabled` is true.   | `string`       | `null`                                                     | no       |
| `ca_bundle_secret_enabled`                | Whether to render/apply a Secret containing the Vault CA bundle                            | `bool`         | `false`                                                    | no       |
| `ca_bundle_secret_name`                   | Name of the Secret containing the Vault CA bundle                                          | `string`       | `"vault-ca-bundle"`                                        | no       |
| `ca_bundle_secret_key`                    | Key in the CA bundle Secret containing the PEM data                                        | `string`       | `"ca.crt"`                                                 | no       |

## Outputs

| Name                                     | Description                                                  |
| ---------------------------------------- | ------------------------------------------------------------ |
| `namespace`                              | Namespace where cert-manager is installed                    |
| `helm_release_name`                      | Name of the cert-manager Helm release                        |
| `acme_staging_issuer_name`               | Name of the ACME staging ClusterIssuer                       |
| `acme_staging_issuer_ref`                | Reference object for the ACME staging ClusterIssuer          |
| `acme_production_issuer_name`            | Name of the ACME production ClusterIssuer                    |
| `acme_production_issuer_ref`             | Reference object for the ACME production ClusterIssuer       |
| `vault_issuer_name`                      | Name of the Vault ClusterIssuer                              |
| `vault_issuer_ref`                       | Reference object for the Vault ClusterIssuer                 |
| `acme_staging_account_key_secret_ref`    | Secret reference for the ACME staging account private key    |
| `acme_production_account_key_secret_ref` | Secret reference for the ACME production account private key |
| `namecheap_api_secret_ref`               | Secret reference holding Namecheap API credentials           |
| `vault_token_secret_ref`                 | Secret reference holding the Vault token                     |
| `vault_ca_bundle_pem`                    | PEM-encoded Vault CA bundle                                  |
| `vault_ca_bundle_base64`                 | Base64-encoded Vault CA bundle used in the Vault issuer      |
| `ca_bundle_secret_ref`                   | Secret reference for the Vault CA bundle (if enabled)        |
| `webhook_release_name`                   | Name of the Namecheap webhook Helm release                   |
| `rendered_manifests`                     | Rendered Flux-ready manifests (render mode only)             |

## Namecheap API secret

Create a Kubernetes secret containing the Namecheap API credentials:

```bash
kubectl create secret generic namecheap-api-credentials \
  --namespace cert-manager \
  --from-literal=api-key=<namecheap-api-key> \
  --from-literal=api-user=<namecheap-api-user>
```

## Vault token secret

Create a Kubernetes secret containing the Vault token:

```bash
kubectl create secret generic vault-token \
  --namespace cert-manager \
  --from-literal=token=<vault-token>
```

## Resources created

When `mode = "apply"`, the module creates:

1. **kubernetes_namespace.cert_manager** (optional) – Namespace
2. **helm_release.cert_manager** – cert-manager Helm chart
3. **helm_release.namecheap_webhook** (optional) – Namecheap webhook Helm chart
4. **kubernetes_manifest.acme_staging_issuer** – ACME staging ClusterIssuer
5. **kubernetes_manifest.acme_production_issuer** – ACME production
   ClusterIssuer
6. **kubernetes_manifest.vault_issuer** – Vault ClusterIssuer
7. **kubernetes_manifest.webhook_pdb** – webhook PodDisruptionBudget (optional)
8. **kubernetes_manifest.cainjector_pdb** – cainjector PodDisruptionBudget
   (optional)
9. **kubernetes_manifest.ca_bundle_secret** – Vault CA bundle Secret (optional)
