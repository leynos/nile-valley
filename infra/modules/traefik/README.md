# Traefik Gateway Module

Deploys [Traefik](https://traefik.io/) as an ingress controller using Helm and
creates a cert-manager ClusterIssuer for Automatic Certificate Management
Environment (ACME) certificate management with Cloudflare DNS-01 challenge
validation.

## Prerequisites

- A Kubernetes cluster with cluster-admin access
- [cert-manager](https://cert-manager.io/) installed in the cluster
- A Kubernetes Secret containing a Cloudflare API token with DNS edit
  permissions
- OpenTofu >= 1.6.0
- `conftest` (policy tests): requires conftest built
  with OPA >= 0.59.0 (Rego v1 syntax)

## Usage

```hcl
module "traefik" {
  source = "path/to/modules/traefik"

  # Apply directly to a cluster (requires providers configured in the caller)
  mode = "apply"

  namespace                        = "traefik"
  acme_email                       = "admin@example.com"
  cloudflare_api_token_secret_name = "cloudflare-api-token"

  # Optional: use staging for testing
  # acme_server = "https://acme-staging-v02.api.letsencrypt.org/directory"
}
```

### Render mode (Flux manifests)

When `mode = "render"`, the module does not talk to a Kubernetes cluster. It
instead returns a `rendered_manifests` map, keyed by the intended GitOps
(Git-based operations) path within the `nile-valley-infra` repository.

## Inputs

| Name                               | Description                                                                       | Type           | Default                                                                    | Required |
| ---------------------------------- | --------------------------------------------------------------------------------- | -------------- | -------------------------------------------------------------------------- | -------- |
| `namespace`                        | Namespace where Traefik will be installed                                         | `string`       | `"traefik"`                                                                | no       |
| `mode`                             | Whether to render Flux manifests (`render`) or apply resources directly (`apply`) | `string`       | `"render"`                                                                 | no       |
| `create_namespace`                 | Whether the module should create the namespace                                    | `bool`         | `true`                                                                     | no       |
| `chart_repository`                 | Helm repository hosting the Traefik chart                                         | `string`       | `"https://traefik.github.io/charts"`                                       | no       |
| `chart_name`                       | Name of the Helm chart                                                            | `string`       | `"traefik"`                                                                | no       |
| `chart_version`                    | Traefik Helm chart version                                                        | `string`       | `"37.4.0"`                                                                 | no       |
| `helm_release_name`                | Name assigned to the Helm release                                                 | `string`       | `"traefik"`                                                                | no       |
| `helm_wait`                        | Whether to wait for the release to succeed                                        | `bool`         | `true`                                                                     | no       |
| `helm_timeout`                     | Timeout in seconds for Helm operations                                            | `number`       | `600`                                                                      | no       |
| `helm_values`                      | Inline YAML values for the Helm release                                           | `list(string)` | `[]`                                                                       | no       |
| `helm_values_files`                | Paths to YAML files with Helm values                                              | `list(string)` | `[]`                                                                       | no       |
| `service_type`                     | Kubernetes service type                                                           | `string`       | `"LoadBalancer"`                                                           | no       |
| `service_annotations`              | Service annotations applied to Traefik's Service                                  | `map(string)`  | `{}`                                                                       | no       |
| `external_traffic_policy`          | Traffic policy (Local preserves client IPs)                                       | `string`       | `"Local"`                                                                  | no       |
| `ingress_class_name`               | Name of the IngressClass                                                          | `string`       | `"traefik"`                                                                | no       |
| `ingress_class_default`            | Set as default IngressClass                                                       | `bool`         | `false`                                                                    | no       |
| `dashboard_enabled`                | Enable the Traefik dashboard                                                      | `bool`         | `false`                                                                    | no       |
| `dashboard_hostname`               | Hostname for dashboard IngressRoute                                               | `string`       | `null`                                                                     | no       |
| `flux_namespace`                   | Namespace where Flux controllers and sources run (render mode)                    | `string`       | `"flux-system"`                                                            | no       |
| `flux_helm_repository_name`        | Flux HelmRepository name for the Traefik chart (render mode)                      | `string`       | `"traefik"`                                                                | no       |
| `http_to_https_redirect`           | Redirect HTTP to HTTPS                                                            | `bool`         | `true`                                                                     | no       |
| `prometheus_metrics_enabled`       | Enable Prometheus metrics                                                         | `bool`         | `true`                                                                     | no       |
| `service_monitor_enabled`          | Create ServiceMonitor for Prometheus Operator                                     | `bool`         | `true`                                                                     | no       |
| `tolerations`                      | Tolerations for pod scheduling                                                    | `list(object)` | `[{"key":"CriticalAddonsOnly","operator":"Exists","effect":"NoSchedule"}]` | no       |
| `acme_email`                       | Email for ACME registration                                                       | `string`       | -                                                                          | **yes**  |
| `acme_server`                      | ACME server URL                                                                   | `string`       | `"https://acme-v02.api.letsencrypt.org/directory"`                         | no       |
| `cluster_issuer_name`              | Name of the ClusterIssuer resource                                                | `string`       | `"letsencrypt-prod"`                                                       | no       |
| `cloudflare_api_token_secret_name` | Kubernetes secret with Cloudflare token                                           | `string`       | -                                                                          | **yes**  |
| `cloudflare_api_token_secret_key`  | Key in the Cloudflare token secret                                                | `string`       | `"token"`                                                                  | no       |

## Outputs

| Name                              | Description                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------ |
| `namespace`                       | Namespace where Traefik is installed                                                 |
| `helm_release_name`               | Name of the Traefik Helm release                                                     |
| `cluster_issuer_name`             | Name of the ClusterIssuer                                                            |
| `cluster_issuer_ref`              | Reference object for use in Certificate resources                                    |
| `dashboard_hostname`              | Dashboard hostname (null if disabled)                                                |
| `dashboard_hostnames`             | Dashboard hostnames (empty unless enabled)                                           |
| `default_certificate_issuer_name` | Name of the default certificate issuer                                               |
| `ingress_class_name`              | Name of the IngressClass                                                             |
| `rendered_manifests`              | Rendered Flux-ready manifests (map of GitOps path -> YAML content; render mode only) |

## Dashboard Security

The Traefik dashboard is disabled by default for security. If enabled, ensure
proper access controls are configured:

```hcl
module "traefik" {
  source = "path/to/modules/traefik"

  mode = "apply"

  dashboard_enabled  = true
  dashboard_hostname = "traefik.internal.example.com"

  # Additional security via Helm values
  helm_values = [<<-YAML
    dashboard:
      enabled: true
    # Consider adding middleware for authentication
    YAML
  ]
}
```

When `dashboard_enabled` is true, the module configures the Traefik Helm
chart's `ingressRoute.dashboard.matchRule` using `dashboard_hostname`.

## ACME Staging

For testing, use the Let's Encrypt staging server to avoid rate limits:

```hcl
module "traefik" {
  source = "path/to/modules/traefik"

  mode = "apply"

  acme_server         = "https://acme-staging-v02.api.letsencrypt.org/directory"
  cluster_issuer_name = "letsencrypt-staging"
  # ...
}
```

Note: Staging certificates are not trusted by browsers.

## Cloudflare API Token

Create a Kubernetes secret containing a Cloudflare API token:

```bash
kubectl create secret generic cloudflare-api-token \
  --namespace cert-manager \
  --from-literal=token=<cloudflare-api-token>
```

The token requires the following permissions:

- Zone: DNS: Edit (for the zones intended for certificate issuance)
- Zone: Zone: Read (to list zones)

## Resources Created

When `mode = "apply"`, the module creates:

1. **kubernetes_namespace.traefik** - Namespace (when `create_namespace = true`)
2. **helm_release.traefik** - Traefik Helm chart deployment
3. **kubernetes_manifest.cluster_issuer** - cert-manager ClusterIssuer

## Integration with Other Modules

Use the outputs to configure other resources:

```hcl
# Certificate for an application
resource "kubernetes_manifest" "certificate" {
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "Certificate"
    metadata = {
      name      = "my-app-tls"
      namespace = "my-app"
    }
    spec = {
      secretName = "my-app-tls"
      issuerRef  = module.traefik.cluster_issuer_ref
      dnsNames   = ["app.example.com"]
    }
  }
}

# Ingress using the Traefik IngressClass
resource "kubernetes_ingress_v1" "my_app" {
  metadata {
    name      = "my-app"
    namespace = "my-app"
  }
  spec {
    ingress_class_name = module.traefik.ingress_class_name
    # ...
  }
}
```
