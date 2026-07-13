# DOKS Module

Provision a DigitalOcean Kubernetes (DOKS) cluster.

Requires [OpenTofu](https://opentofu.org/docs/intro/install/) 1.6 or later.

## Quick start

Set the `DIGITALOCEAN_TOKEN` environment variable to allow provider
authentication:

```sh
export DIGITALOCEAN_TOKEN="<DIGITALOCEAN_TOKEN>"
```

Configure the provider, call the module, and expose outputs:

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    digitalocean = {
      source  = "opentofu/digitalocean"
      version = "~> 2.36"
    }
  }
}

provider "digitalocean" {}

module "doks" {
  # Prefer a released tag or a commit SHA for reproducibility
  source = "git::https://github.com/OWNER/nile-valley.git//infra/modules/doks?ref=<TAG_OR_SHA>"

  cluster_name       = "example"
  region             = "nyc1"
  kubernetes_version = "<SUPPORTED_VERSION_SLUG>"

  node_pools = [{
    name       = "default"
    size       = "s-2vcpu-4gb"
    node_count = 3
    auto_scale = false
  }]

  expose_kubeconfig = true
}

output "endpoint" {
  value = module.doks.cluster_endpoint
}

output "kubeconfig" {
  value     = module.doks.kubeconfig
  sensitive = true
}
```

> Note: Select a supported Kubernetes version from DigitalOcean's current list
> of DOKS releases (typically the latest three minor versions). See the version
> table for current releases:
> <https://docs.digitalocean.com/products/kubernetes/details/supported-releases/>.
>
> Caution: Sensitive outputs persist in state. Store state in an encrypted,
> access‑controlled backend and restrict state access to authorized
> principals. Rotate the DigitalOcean token and cluster credentials if state
> exposure is suspected.

Enable `auto_scale` and define `min_nodes` and `max_nodes` to scale between
bounds. These settings have no effect when `auto_scale` is `false`.

Retrieve the kubeconfig and cluster endpoint after applying the configuration:

```sh
tofu output -raw kubeconfig > kubeconfig.yaml
chmod 600 kubeconfig.yaml
tofu output endpoint
```

Consult the DigitalOcean provider documentation for advanced configuration:
<https://search.opentofu.org/provider/opentofu/digitalocean/latest>

Substitute `OWNER` with the GitHub account name and `<TAG_OR_SHA>` with the
tagged release or commit to use.
