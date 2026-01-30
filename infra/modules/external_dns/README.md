# ExternalDNS Module

Deploys [ExternalDNS](https://github.com/kubernetes-sigs/external-dns) as a DNS
automation controller using Helm. ExternalDNS watches Kubernetes resources
(Ingress, Service) and automatically manages DNS records in Cloudflare based on
annotations.

## Prerequisites

- A Kubernetes cluster with cluster-admin access
- A Kubernetes Secret containing a Cloudflare API token with appropriate
  permissions
- OpenTofu >= 1.6.0
- `conftest` (policy tests): requires conftest built with OPA >= 0.59.0
  (Rego v1 syntax)

## Usage

```hcl
module "external_dns" {
  source = "path/to/modules/external_dns"

  # Apply directly to a cluster (requires providers configured in the caller)
  mode = "apply"

  namespace                        = "external-dns"
  domain_filters                   = ["example.com", "example.org"]
  txt_owner_id                     = "production-cluster-01"
  cloudflare_api_token_secret_name = "cloudflare-api-token"
}
```

### Render mode (Flux manifests)

When `mode = "render"`, the module does not talk to a Kubernetes cluster. It
instead returns a `rendered_manifests` map, keyed by the intended GitOps
(Git-based operations) path within the `nile-valley-infra` repository.

```hcl
module "external_dns" {
  source = "path/to/modules/external_dns"

  mode = "render"

  domain_filters                   = ["example.com"]
  txt_owner_id                     = "dev-cluster"
  cloudflare_api_token_secret_name = "cloudflare-api-token"
}

# Write rendered manifests to files
resource "local_file" "manifests" {
  for_each = module.external_dns.rendered_manifests

  filename = "${path.module}/output/${each.key}"
  content  = each.value
}
```

## Inputs

| Name                               | Description                                                                       | Type           | Default                                             | Required |
| ---------------------------------- | --------------------------------------------------------------------------------- | -------------- | --------------------------------------------------- | -------- |
| `namespace`                        | Namespace where ExternalDNS will be installed                                     | `string`       | `"external-dns"`                                    | no       |
| `mode`                             | Whether to render Flux manifests (`render`) or apply resources directly (`apply`) | `string`       | `"render"`                                          | no       |
| `create_namespace`                 | Whether the module should create the namespace                                    | `bool`         | `true`                                              | no       |
| `chart_repository`                 | Helm repository hosting the ExternalDNS chart                                     | `string`       | `"https://kubernetes-sigs.github.io/external-dns/"` | no       |
| `chart_name`                       | Name of the Helm chart                                                            | `string`       | `"external-dns"`                                    | no       |
| `chart_version`                    | ExternalDNS Helm chart version                                                    | `string`       | `"1.16.1"`                                          | no       |
| `helm_release_name`                | Name assigned to the Helm release                                                 | `string`       | `"external-dns"`                                    | no       |
| `helm_wait`                        | Whether to wait for the release to succeed                                        | `bool`         | `true`                                              | no       |
| `helm_timeout`                     | Timeout in seconds for Helm operations                                            | `number`       | `600`                                               | no       |
| `helm_values`                      | Inline YAML values for the Helm release                                           | `list(string)` | `[]`                                                | no       |
| `helm_values_files`                | Paths to YAML files with Helm values                                              | `list(string)` | `[]`                                                | no       |
| `domain_filters`                   | List of DNS domains that ExternalDNS should manage                                | `list(string)` | -                                                   | **yes**  |
| `txt_owner_id`                     | Unique identifier for ExternalDNS ownership TXT records                           | `string`       | -                                                   | **yes**  |
| `policy`                           | DNS record management policy                                                      | `string`       | `"sync"`                                            | no       |
| `sources`                          | Kubernetes resource types to watch                                                | `list(string)` | `["ingress", "service"]`                            | no       |
| `cloudflare_api_token_secret_name` | Kubernetes secret with Cloudflare token                                           | `string`       | -                                                   | **yes**  |
| `cloudflare_api_token_secret_key`  | Key in the Cloudflare token secret                                                | `string`       | `"token"`                                           | no       |
| `cloudflare_proxied`               | Enable Cloudflare proxy by default                                                | `bool`         | `false`                                             | no       |
| `dns_records_per_page`             | API pagination size (reduces API calls)                                           | `number`       | `5000`                                              | no       |
| `log_level`                        | Log verbosity level                                                               | `string`       | `"info"`                                            | no       |
| `crd_enabled`                      | Enable the DNSEndpoint CRD                                                        | `bool`         | `true`                                              | no       |
| `service_monitor_enabled`          | Create ServiceMonitor for Prometheus Operator                                     | `bool`         | `false`                                             | no       |
| `flux_namespace`                   | Namespace where Flux controllers run (render mode)                                | `string`       | `"flux-system"`                                     | no       |
| `flux_helm_repository_name`        | Flux HelmRepository name (render mode)                                            | `string`       | `"external-dns"`                                    | no       |
| `interval`                         | Interval between DNS synchronization cycles                                       | `string`       | `"1m"`                                              | no       |
| `registry_type`                    | Registry type for tracking DNS record ownership                                   | `string`       | `"txt"`                                             | no       |
| `txt_prefix`                       | Prefix for TXT ownership records                                                  | `string`       | `""`                                                | no       |
| `txt_suffix`                       | Suffix for TXT ownership records                                                  | `string`       | `""`                                                | no       |
| `zone_id_filter`                   | Map of domain names to Cloudflare zone IDs                                        | `map(string)`  | `{}`                                                | no       |

## Outputs

| Name                 | Description                                                                          |
| -------------------- | ------------------------------------------------------------------------------------ |
| `namespace`          | Namespace where ExternalDNS is installed                                             |
| `helm_release_name`  | Name of the ExternalDNS Helm release                                                 |
| `txt_owner_id`       | Unique identifier for ExternalDNS ownership TXT records                              |
| `domain_filters`     | List of DNS domains managed by ExternalDNS                                           |
| `zone_id_filter`     | Map of domain names to Cloudflare zone IDs                                           |
| `managed_zones`      | Unified zone configuration: domain -> zone_id (null if not specified)                |
| `policy`             | DNS record management policy                                                         |
| `sources`            | Kubernetes resource types watched by ExternalDNS                                     |
| `cloudflare_proxied` | Whether Cloudflare proxy is enabled by default                                       |
| `rendered_manifests` | Rendered Flux-ready manifests (map of GitOps path -> YAML content; render mode only) |

## Cloudflare API Token

Create a Kubernetes secret containing a Cloudflare API token:

```bash
kubectl create secret generic cloudflare-api-token \
  --namespace external-dns \
  --from-literal=token=<cloudflare-api-token>
```

The token requires the following permissions:

- Zone: DNS: Edit (for the zones intended for DNS record management)
- Zone: Zone: Read (to list zones)

For security, scope the token to the specific zones being managed rather than
granting access to all zones in the account.

## Multi-Zone Support

ExternalDNS can manage DNS records across multiple domains. Simply provide all
domains in the `domain_filters` list:

```hcl
module "external_dns" {
  source = "path/to/modules/external_dns"

  mode = "apply"

  domain_filters = [
    "example.com",
    "example.org",
    "staging.example.net",
  ]

  txt_owner_id                     = "production-cluster"
  cloudflare_api_token_secret_name = "cloudflare-api-token"
}
```

## Zone ID Filter (Optional)

The `zone_id_filter` variable allows restricting ExternalDNS API access to
specific Cloudflare zones. This provides defence-in-depth beyond
`domain_filters` and enables zone ID output for downstream consumers.

```hcl
module "external_dns" {
  source = "path/to/modules/external_dns"

  mode = "apply"

  domain_filters = ["example.com", "example.org"]
  zone_id_filter = {
    "example.com" = "abc123def456789012345678901234ab"
    "example.org" = "def456abc789012345678901234567cd"
  }

  txt_owner_id                     = "production-cluster"
  cloudflare_api_token_secret_name = "cloudflare-api-token"
}

# Access zone IDs for downstream consumers
output "zone_mapping" {
  value = module.external_dns.managed_zones
  # Returns: { "example.com" = "abc123...", "example.org" = "def456..." }
}
```

Zone IDs are 32-character hexadecimal strings, available in the Cloudflare
dashboard under the zone's Overview page (right sidebar).

## DNS Record Ownership

The `txt_owner_id` parameter is critical for safe multi-cluster or multi-tenant
operation. ExternalDNS creates TXT records to track ownership of DNS records it
manages. This prevents:

- Conflicts between multiple ExternalDNS instances
- Accidental deletion of records managed by other controllers
- Cross-cluster interference in shared DNS zones

Always use a unique `txt_owner_id` for each ExternalDNS deployment.

## Resources Created

When `mode = "apply"`, the module creates:

1. **kubernetes_namespace.external_dns** - Namespace (when
   `create_namespace = true`)
2. **helm_release.external_dns** - ExternalDNS Helm chart deployment

## Integration with Ingress Resources

Once ExternalDNS is deployed, annotate Ingress resources to trigger automatic
DNS record creation:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  annotations:
    external-dns.alpha.kubernetes.io/hostname: my-app.example.com
    external-dns.alpha.kubernetes.io/cloudflare-proxied: "true"
    external-dns.alpha.kubernetes.io/ttl: "120"
spec:
  ingressClassName: traefik
  rules:
    - host: my-app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 80
```

## DNSEndpoint Custom Resource

When `crd_enabled = true`, DNS records can be created declaratively using the
DNSEndpoint CRD:

```yaml
apiVersion: externaldns.k8s.io/v1alpha1
kind: DNSEndpoint
metadata:
  name: static-record
  namespace: default
spec:
  endpoints:
    - dnsName: static.example.com
      recordType: A
      recordTTL: 300
      targets:
        - "192.0.2.100"
```

## Troubleshooting

### No DNS records created

1. Check ExternalDNS logs:

   ```bash
   kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -f
   ```

2. Verify the Cloudflare API token has correct permissions
3. Ensure `domain_filters` includes the domain being managed
4. Check that the Ingress/Service has the correct annotations

### Stale DNS records not deleted

1. Ensure `policy = "sync"` (not `upsert-only`)
2. Verify `txt_owner_id` matches the original deployment

### API rate limiting

If rate limit errors occur:

1. Increase `dns_records_per_page` to reduce API calls
2. Increase `interval` to reduce synchronization frequency
