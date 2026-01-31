terraform {
  required_version = ">= 1.6.0, < 2.0.0"
  required_providers {
    digitalocean = {
      source  = "opentofu/digitalocean"
      version = "~> 2.74.0"
    }

    kubernetes = {
      source  = "opentofu/kubernetes"
      version = "~> 3.0.1"
    }

    helm = {
      source  = "opentofu/helm"
      version = "~> 3.1.1"
    }
  }
}
