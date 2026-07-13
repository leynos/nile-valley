# Declarative TLS: A GitOps Blueprint for Automated Certificate Management in Kubernetes

## Introduction: Completing the Automation Pipeline

The modern cloud-native landscape, orchestrated by platforms like Kubernetes,
demands a paradigm shift from imperative, manual operations to declarative,
automated workflows. A foundational element of this shift, detailed in the
complementary guide [Declarative DNS](../declarative-dns-guide.md), is the
automation of DNS management using a GitOps-centric architecture. This approach
establishes a Git repository as the single source of truth (SSOT), with
controllers like FluxCD and ExternalDNS continuously reconciling the cluster's
state to match the declarative configurations committed to Git. This model
successfully decouples application deployment from the once-manual process of
creating public DNS records, dramatically increasing development velocity and
operational reliability.[^1]

However, a publicly accessible endpoint is incomplete without robust security.
The logical and necessary next step in this automation journey is to apply the
same GitOps principles to the lifecycle of TLS certificates. Manually
provisioning, renewing, and configuring certificates introduces the same
bottlenecks and risks of human error that automated DNS was designed to
eliminate. An application may be discoverable via DNS, but it remains insecure
and untrusted by clients until a valid TLS certificate is in place.

This report details a comprehensive, production-grade architecture for
achieving "TLS-as-Code." By integrating cert-manager, the de-facto standard for
certificate automation in Kubernetes, into the existing GitOps ecosystem, we
can complete the application exposure pipeline.[^2] The architectural vision
is to enable a seamless, end-to-end workflow where a single `git push` of a
standard Kubernetes Ingress manifest triggers a chain of automated events:
FluxCD applies the manifest, ExternalDNS creates the necessary public DNS
record, and cert-manager provisions a valid, trusted TLS certificate from
Let's Encrypt. The result is a fully secure, publicly accessible application
endpoint, brought online in minutes with zero manual intervention.

This solution leverages a synergistic stack of components, each with a
well-defined role, to create a resilient and secure system. This report will
provide a deep dive into the provisioning of the foundational infrastructure on
DigitalOcean Kubernetes (DOKS) using OpenTofu, the secure deployment of the TLS
automation stack via FluxCD, the intricacies of integrating with a
Namecheap-provided domain, and advanced strategies for overcoming
provider-specific challenges to ensure operational excellence.

The following table expands upon the architectural blueprint to include the
components responsible for TLS automation, providing a holistic view of the
integrated system.

| Component                          | Primary Role                   | Scope of Control                                                                    | Managed By                           |
| ---------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------ |
| Kubernetes                         | Application Orchestration      | Manages the lifecycle of containers, Pods, Services, and Ingresses.                 | Platform/Application Teams           |
| DigitalOcean                       | Cloud & IaaS Provider          | Hosts the DOKS cluster, VPC networking, and optional NAT Gateways.                  | OpenTofu                             |
| Namecheap                          | Domain Registrar & DNS         | Hosts the authoritative domain and provides an API for DNS record management.       | OpenTofu (Domain), Webhook (Records) |
| OpenTofu                           | Infrastructure as Code Tool    | Provisions and manages the foundational DOKS cluster and Namecheap domain settings. | Platform Team                        |
| FluxCD                             | GitOps Operator                | Synchronizes the entire Kubernetes cluster state with a Git repository.             | Platform Team                        |
| ExternalDNS                        | DNS Automation Controller      | Translates Kubernetes resources into DNS records (via provider API).                | FluxCD                               |
| **cert-manager**                   | **TLS Automation Controller**  | Manages the lifecycle of `Certificate`, `Issuer`, and other TLS-related resources.  | **FluxCD**                           |
| **cert-manager-webhook-namecheap** | **DNS-01 Challenge Solver**    | Acts as a plugin for cert-manager to create/delete TXT records in Namecheap's DNS.  | **FluxCD**                           |
| **Let's Encrypt**                  | **Certificate Authority (CA)** | Issues publicly trusted TLS certificates via the ACME protocol.                     | cert-manager                         |

## Part 1: Foundational Infrastructure with OpenTofu

Before deploying the in-cluster components of the TLS automation stack, a solid
foundation of cloud and domain infrastructure must be provisioned
declaratively. OpenTofu, as the Infrastructure as Code (IaC) tool, is
responsible for managing these long-lived, foundational resources. This ensures
a clear separation of concerns between the underlying infrastructure managed by
the platform team and the dynamic, in-cluster resources managed by the GitOps
workflow.[^1]

### 1.1 OpenTofu Provider Configuration

To interact with the APIs of DigitalOcean and Namecheap, OpenTofu requires the
configuration of their respective providers. This is defined within a
`terraform` block, which specifies the required providers, their source
addresses, and version constraints to ensure predictable and repeatable
deployments.[^3]

It is a critical security best practice to manage API credentials outside
version-controlled configuration files. The DigitalOcean and Namecheap
providers can be configured to read credentials from environment variables,
which is the recommended approach.[^4]

**OpenTofu Provider Configuration (**`providers.tf`**):**

```terraform
terraform {
  required_providers {
    digitalocean = {
      source  = "opentofu/digitalocean"
      version = "~> 2.0"
    }
    namecheap = {
      source  = "namecheap/namecheap"
      version = ">= 2.0.0"
    }
  }
}

# Configure the DigitalOcean Provider
# Credentials sourced from DIGITALOCEAN_TOKEN environment variable
provider "digitalocean" {}

# Configure the Namecheap Provider
# Credentials sourced from NAMECHEAP_API_USER and NAMECHEAP_API_KEY env vars
provider "namecheap" {
  user_name = var.namecheap_api_user
  api_user  = var.namecheap_api_user
  api_key   = var.namecheap_api_key
  client_ip = var.namecheap_client_ip
}

variable "namecheap_api_user" {
  type        = string
  description = "Namecheap API User (same as account username)."
  sensitive   = true
}

variable "namecheap_api_key" {
  type        = string
  description = "Namecheap API Key."
  sensitive   = true
}

variable "namecheap_client_ip" {
  type        = string
  description = "The public IP address whitelisted in the Namecheap account."
}

```

The `client_ip` argument in the Namecheap provider configuration is
particularly noteworthy, as it directly relates to a significant operational
constraint that will be addressed later in this report.

### 1.2 Provisioning the DigitalOcean Kubernetes (DOKS) Cluster

The DOKS cluster is the heart of the platform. Using the
`digitalocean_kubernetes_cluster` resource, its entire configuration can be
managed as code. For a production environment, it is essential to configure the
cluster for high availability and resilience.[^5]

**DOKS Cluster Configuration (**`doks.tf`**):**

```terraform
resource "digitalocean_kubernetes_cluster" "primary" {
  name    = "production-cluster-01"
  region  = "nyc3"
  version = "1.28.4-do.0" // Specify a stable, recent version

  # Enable automatic patch version upgrades within a defined maintenance window
  auto_upgrade = true
  maintenance_policy {
    day        = "saturday"
    start_time = "03:00"
  }

  # Define the default node pool for cluster components
  node_pool {
    name       = "default-pool"
    size       = "s-4vcpu-8gb" // Choose an appropriate instance size
    node_count = 3

    # Optional: Enable auto-scaling for the node pool
    auto_scale = true
    min_nodes  = 3
    max_nodes  = 7
  }

  tags = ["env:production", "gitops-managed"]
}

```

DigitalOcean provides a highly available control plane by default, mitigating
the risk of a single-point-of-failure for the Kubernetes API server. This
configuration also enables automatic patch upgrades (`auto_upgrade = true`)
during a non-critical maintenance window, ensuring the cluster remains secure
and up-to-date with minimal operational overhead.[^5]

### 1.3 Managing the Namecheap Domain and API

Proper configuration of the Namecheap account and API is a prerequisite for any
automation.

#### 1.3.1 API Credential Generation

To enable programmatic access, API access must be activated within the
Namecheap account dashboard. This process has specific prerequisites that must
be met.[^6]

1. **Meet Prerequisites:** Ensure the account meets at least one of the
   following criteria:

   - Has at least 20 domains registered.
   - Has an account balance of at least $50.
   - Has spent at least $50 in the last two years.

2. **Enable API Access:**

   - Log in to the Namecheap account.
   - Navigate to `Profile` > `Tools`.
   - Scroll to the "Business & Dev Tools" section and click `MANAGE` next to
     "Namecheap API Access."
   - Toggle the feature `ON`, accept the terms, and enter the account
     password.[^7]

3. **Retrieve Credentials:** Once enabled, the system will provide an `APIKey`.
   The `API User` is the same as the Namecheap account username. These two
   values are the credentials required for the OpenTofu provider and the
   in-cluster webhook.

#### 1.3.2 The Critical Constraint: IP Address Whitelisting

A critical examination of the Namecheap API reveals a mandatory IP whitelisting
requirement. This presents a fundamental architectural conflict with the
dynamic, ephemeral nature of pod networking in a managed Kubernetes environment
like DOKS, where egress IPs are non-deterministic.

- **The Requirement:** The Namecheap API will only accept requests from IP
  addresses that have been explicitly added to a whitelist in the account's API
  settings.[^8]
- **The Limitations:** This whitelist has several restrictive limitations:

  - It only supports single, static IPv4 addresses, and only a limited number of
    IPs may be whitelisted.[^9]
  - The process of adding an IP to the whitelist is manual, via the Namecheap
    dashboard.
- **The Conflict:** The `cert-manager-webhook-namecheap` pod, which is
  responsible for making these API calls, will be scheduled on any of the
  worker nodes in the DOKS cluster. The public IP address used for its outbound
  traffic (its egress IP) will be the IP of the node it is currently running
  on. Worker nodes in a managed Kubernetes service are considered ephemeral;
  they can be replaced during upgrades, scaling events, or failures. When a
  node is replaced, it receives a new public IP address. This new IP will not
  be on the whitelist, causing all API calls from the webhook to fail until an
  operator manually intervenes to update the whitelist. This breaks the core
  principle of automation and makes any direct integration inherently brittle
  and unsuitable for production.[^9]

This constraint is the single most significant technical challenge in this
architecture. A robust, production-grade solution _must_ incorporate a strategy
to mitigate this issue, which will be the focus of Part 5.

### 1.4 Declarative Domain Configuration

While dynamic, application-specific DNS records will be managed by in-cluster
controllers, foundational records (like those for email) or the nameserver
delegation itself can be managed via OpenTofu using the
`namecheap_domain_records` resource.[^10]

A crucial detail of this resource is that the `record` and `nameservers`
arguments are mutually exclusive. A single `namecheap_domain_records` resource
block cannot be used to set both custom nameservers and other record types like
`A` or `TXT` simultaneously.[^10] This is an important consideration for the
DNS delegation strategy discussed in Part 5, as it implies that managing the
delegation will require a dedicated resource block separate from any other
record management.

## Part 2: GitOps-Driven Deployment of the TLS Automation Stack

With the foundational infrastructure in place, the focus shifts to deploying
the in-cluster controllers that will perform the TLS automation. Adhering to
GitOps principles, the entire lifecycle of these components—installation,
configuration, and upgrades—will be managed declaratively through Kubernetes
manifests stored in the Git repository and reconciled by FluxCD.[^1]

### 2.1 Secure Credential Management with Mozilla SOPS

The Namecheap API credentials are highly sensitive and must never be stored in
plain text in the Git repository. Mozilla SOPS (Secrets OPerationS) is a
powerful tool that integrates seamlessly with FluxCD to enable end-to-end
encryption for secrets.[^11] The workflow ensures that secrets are encrypted
before being committed to Git and are only decrypted by the FluxCD controller
in-memory just before being applied to the cluster.[^11]

The SOPS workflow proceeds as follows:

1. **Generate an Encryption Key:** A GPG key (or an alternative like Age) is
   generated locally. This key will be used to encrypt and decrypt the
   secrets.[^12]
2. **Store the Decryption Key in the Cluster:** The private portion of the GPG
   key is stored in the Kubernetes cluster as a standard `Secret` resource,
   typically in the `flux-system` namespace. This allows the FluxCD
   `kustomize-controller` to access it for decryption.[^11]

    ```bash
    # (Assuming GPG key is already generated)
    gpg --export-secret-keys --armor <KEY_FINGERPRINT> | \
      kubectl create secret generic sops-gpg \
      --namespace=flux-system \
      --from-file=sops.asc=/dev/stdin

    ```

3. **Create and Encrypt the Namecheap Secret:** A standard Kubernetes `Secret`
   manifest is created locally to hold the Namecheap API credentials. The
   `sops` CLI is then used to encrypt the `data` field of this manifest.

    ```yaml
    # namecheap-api-credentials.yaml (before encryption)
    apiVersion: v1
    kind: Secret
    metadata:
      name: namecheap-api-credentials
      namespace: cert-manager
    stringData:
      api-key: "YOUR_NAMECHEAP_API_KEY"
      api-user: "YOUR_NAMECHEAP_USERNAME"

    ```

    ```bash
    # Encrypt the secret in-place
    sops --encrypt --in-place namecheap-api-credentials.yaml

    ```

4. **Commit the Encrypted Secret:** The resulting encrypted file is safe to
   commit to the Git repository.
5. **Configure FluxCD for Decryption:** The `Kustomization` resource in FluxCD
   that points to the directory containing the encrypted secret must be
   configured to enable decryption.

    ```yaml
    # infrastructure/controllers/kustomization.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: cert-manager-stack
      namespace: flux-system
    spec:
      #... other settings
      decryption:
        provider: sops
        secretRef:
          name: sops-gpg

    ```

This setup ensures that sensitive credentials remain encrypted at rest in Git
and are only handled in plain text within the secure confines of the cluster's
control plane.[^11]

| Key in Secret | Description                                                   | Example Value        |
| ------------- | ------------------------------------------------------------- | -------------------- |
| `api-key`     | The API key generated from the Namecheap dashboard.           | `<REDACTED_API_KEY>` |
| `api-user`    | The Namecheap account username, which serves as the API user. | `mynamecheapuser`    |

### 2.2 Deploying cert-manager via HelmRelease

FluxCD manages Helm chart deployments declaratively using the `HelmRepository`
and `HelmRelease` custom resources. This approach treats Helm releases as
version-controlled artifacts, enabling automated, repeatable deployments.[^13]

First, a `HelmRepository` source is defined to tell FluxCD where to find the
cert-manager charts. The official OCI registry provided by Jetstack is the
recommended source.[^14]

`HelmRepository`**for cert-manager (**`infrastructure/sources/helm.yaml`**):**

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: jetstack
  namespace: flux-system
spec:
  interval: 24h
  type: oci
  url: oci://quay.io/jetstack/charts

```

Next, a `HelmRelease` manifest is created to deploy cert-manager. This manifest
specifies the chart version, release configuration, and values that override
the chart's defaults. For a production deployment, it is crucial to configure
for high availability by increasing the replica counts for the controller and
webhook components.[^15]

`HelmRelease`**for cert-manager
(**`infrastructure/controllers/cert-manager.yaml`**):**

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: cert-manager
  namespace: cert-manager
spec:
  interval: 1h
  chart:
    spec:
      chart: cert-manager
      version: "v1.19.2" # Pin to a stable version (align with [^15]) ([cert-manager.io](https://cert-manager.io/docs/installation/helm/?utm_source=openai))
      sourceRef:
        kind: HelmRepository
        name: jetstack
        namespace: flux-system
  install:
    crds:
      enabled: true # cert-manager.io/docs/installation/helm/?utm_source=openai
    remediation:
      retries: 3
  upgrade:
    remediation:
      retries: 3
  values:
    # Production-grade settings for high availability
    replicaCount: 3
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 250m
        memory: 256Mi
    webhook:
      replicaCount: 3
      resources:
        requests: { cpu: 50m, memory: 64Mi }
        limits:   { cpu: 200m, memory: 128Mi }
    cainjector:
      replicaCount: 3
      resources:
        requests: { cpu: 50m, memory: 64Mi }
        limits:   { cpu: 200m, memory: 128Mi }
    # When replicaCount > 1, define PodDisruptionBudgets for webhook and cainjector
    # to maintain availability during voluntary disruptions (drains/evictions).

```

Define PodDisruptionBudgets for the webhook and cainjector when scaling above a
single replica:

```yaml
# examples/pdb-cert-manager-webhook.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cert-manager-webhook-pdb
  namespace: cert-manager
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: webhook
      app.kubernetes.io/instance: cert-manager
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cert-manager-cainjector-pdb
  namespace: cert-manager
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: cainjector
      app.kubernetes.io/instance: cert-manager
```

Reference these manifests in the controllers' kustomization to apply them with
FluxCD:

```yaml
# infrastructure/controllers/kustomization.yaml
resources:
  - cert-manager.yaml
  - examples/pdb-cert-manager-webhook.yaml
  - examples/pdb-cert-manager-cainjector.yaml
```

### 2.3 Deploying the Namecheap DNS-01 Webhook Solver

Cert-manager's core distribution does not include a DNS-01 solver for
Namecheap. To integrate with Namecheap, a third-party webhook solver is
required. This webhook is an external service that cert-manager calls to
fulfil the DNS-01 challenge by creating and deleting the necessary TXT records
via the Namecheap API.[^16]

A critical security assessment of the available community-provided webhooks is
necessary. The options available on public repositories like ArtifactHub and
GitHub are often several years old, are not signed by their authors, and come
from unverified publishers.[^17] Deploying an unmaintained and untrusted
container image directly into a production cluster, especially one that handles
API credentials, represents a significant supply chain security risk.

The most responsible and secure approach is to treat this third-party code as
untrusted and take ownership of its lifecycle:

1. **Fork the Repository:** Fork a well-regarded community webhook repository
   (e.g., `jamesgoodhouse/cert-manager-webhook-namecheap` or
   `kelvie/cert-manager-webhook-namecheap`) into a private version control
   system.
2. **Audit and Update:** Review the code for vulnerabilities and update its
   dependencies.
3. **Build and Push:** Create a CI pipeline to build a new container image from
   the forked source code and push it to a trusted, private container registry,
   such as DigitalOcean Container Registry.
4. **Package and Deploy:** Package the deployment manifests as a private Helm
   chart and host it in a private chart repository.

This process mitigates the risk of running potentially compromised or outdated
code in the cluster. The following `HelmRelease` example assumes such a private
chart has been created.

`HelmRelease`**for Namecheap Webhook
(**`infrastructure/controllers/namecheap-webhook.yaml`**):**

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: cert-manager-webhook-namecheap
  namespace: cert-manager
spec:
  interval: 1h
  chart:
    spec:
      chart: cert-manager-webhook-namecheap
      version: "0.2.0" # Version of your private chart
      sourceRef:
        kind: HelmRepository
        name: private-helm-repo # Assumes a HelmRepository for your private repo
        namespace: flux-system
  values:
    # Ensure the webhook runs with multiple replicas for availability
    replicaCount: 2
    # The groupName must match what is configured in the ClusterIssuer
    groupName: acme.example.com

```

## Part 3: Configuring Declarative Certificate Issuance

With the cert-manager controller and the Namecheap webhook deployed, the next
step is to configure the resources that define how certificates will be issued.
The `ClusterIssuer` resource is the central point of this configuration, acting
as a certificate authority that can be used to sign certificate requests from
any namespace in the cluster.[^18]

### 3.1 Crafting the Let's Encrypt `ClusterIssuer`

It is a crucial best practice to use the Let's Encrypt staging environment for
all development and testing. The staging API has much higher rate limits and
issues certificates from a non-trusted root, making it ideal for verifying
configurations without the risk of being rate-limited by the production API.
Therefore, two `ClusterIssuer` resources should be created: one for staging and
one for production.

These resources encapsulate all the logic for communicating with the ACME
server and solving challenges. This creates a powerful abstraction layer;
application developers only need to reference the name of the `ClusterIssuer`
without needing to know any of the underlying details about DNS providers, API
keys, or challenge mechanisms.

**Staging **`ClusterIssuer`**
(**`infrastructure/issuers/staging-issuer.yaml`**):**

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    # The ACME server URL for Let's Encrypt's staging environment.
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: platform-eng@example.com
    privateKeySecretRef:
      # Secret resource that will be used to store the ACME account's private key.
      name: letsencrypt-staging-account-key
    solvers:
      - dns01:
          webhook:
            groupName: acme.example.com # Must match the groupName in the webhook's HelmRelease
            solverName: namecheap
            config:
              apiKeySecretRef:
                name: namecheap-api-credentials
                key: api-key
              apiUserSecretRef:
                name: namecheap-api-credentials
                key: api-user

```

**Production **`ClusterIssuer`**
(**`infrastructure/issuers/production-issuer.yaml`**):**

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-production
spec:
  acme:
    # The ACME server URL for Let's Encrypt's production environment.
    server: https://acme-v02.api.letsencrypt.org/directory
    email: platform-eng@example.com
    privateKeySecretRef:
      name: letsencrypt-production-account-key
    solvers:
      - dns01:
          webhook:
            groupName: acme.example.com
            solverName: namecheap
            config:
              apiKeySecretRef:
                name: namecheap-api-credentials
                key: api-key
              apiUserSecretRef:
                name: namecheap-api-credentials
                key: api-user

```

### 3.2 Deep Dive into the DNS-01 Webhook Solver Configuration

The `solvers` block is the most critical part of the `ClusterIssuer`
configuration. It instructs cert-manager on how to satisfy the ACME challenges
required to prove domain ownership.[^19] For the Namecheap integration, the
`dns01` solver is configured to use the deployed webhook.[^16].

- `dns01`: Specifies that the DNS-01 challenge type will be used. This involves
  creating a specific TXT record in the domain's DNS zone.
- `webhook`: Indicates that a generic external webhook will be used to perform
  the DNS modifications.
- `groupName`: This is the routing key. It must exactly match the API group
  that the webhook pod registers with the Kubernetes API server. When
  cert-manager needs to solve a challenge, it looks for a webhook solver
  registered with this group name.
- `solverName`: A descriptive name for this specific solver instance.
- `config`: This block contains arbitrary key-value pairs that are passed
  directly to the webhook solver. The webhook's documentation or source code
  dictates the expected keys. For the Namecheap webhook, it requires references
  to the Kubernetes secret containing the API credentials, specified via
  `apiKeySecretRef` and `apiUserSecretRef`. This configuration securely
  connects the `ClusterIssuer` to the SOPS-encrypted secret created in Part 2.

## Part 4: Automated Certificate Management in Action

With all the components deployed and configured via the GitOps workflow, the
system is now ready to automate the entire lifecycle of TLS certificates. The
process is triggered declaratively by application developers as part of their
standard deployment manifests.

### 4.1 The Primary Workflow: Annotating Ingress for TLS

The most common method for requesting a certificate is by annotating a
Kubernetes Ingress resource. This aligns perfectly with the GitOps model, as
the intent to secure an endpoint is declared alongside the routing
configuration for that endpoint.

To enable automated TLS, two key sections are added to the Ingress manifest:

1. **Annotation:** The `cert-manager.io/cluster-issuer` annotation tells
   cert-manager that it should manage the TLS certificate for this Ingress. The
   value of the annotation specifies which `ClusterIssuer` to use (e.g.,
   `letsencrypt-production`).
2. **TLS Block:** The `spec.tls` block defines which hosts on the Ingress
   should be secured and provides the name of the Kubernetes `Secret` where the
   signed certificate and private key will be stored.[^20]

**Example Ingress with TLS Automation (**`my-app/ingress.yaml`**):**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ingress
  namespace: my-app
  annotations:
    # This annotation triggers cert-manager
    cert-manager.io/cluster-issuer: letsencrypt-production
    # This annotation triggers ExternalDNS (from the complementary DNS solution)
    external-dns.alpha.kubernetes.io/hostname: my-app.example.com
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - my-app.example.com
      # cert-manager will store the certificate in this secret
      secretName: my-app-tls-secret
  rules:
    - host: "my-app.example.com"
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app-service
                port:
                  number: 80

```

When this manifest is committed to the Git repository, FluxCD applies it to the
cluster. Cert-manager's controller detects the new Ingress with the annotation
and begins the issuance process, creating the necessary `Certificate`,
`CertificateRequest`, `Order`, and `Challenge` resources automatically.

### 4.2 Issuing Wildcard Certificates

Wildcard certificates are invaluable for environments with dynamic, per-tenant
subdomains or for simplifying the management of multiple services under a
single domain. A single wildcard certificate for `*.example.com` can secure any
number of subdomains like `api.example.com`, `dashboard.example.com`, etc.

A critical requirement from Let's Encrypt is that wildcard certificates can
**only** be issued using the DNS-01 challenge method.[^21] The HTTP-01
challenge, which involves serving a file from a web server, cannot prove
control over an entire domain and is therefore not supported for wildcards.
This makes the successful integration of the DNS-01 webhook solver a mandatory
prerequisite for this use case.

Requesting a wildcard certificate is as simple as specifying the wildcard
domain in the `spec.tls` block of the Ingress.

**Example Ingress for a Wildcard Certificate:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: wildcard-ingress
  namespace: default
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-production
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        # Specify the wildcard domain
        - "*.apps.example.com"
      secretName: wildcard-apps-tls-secret
  rules:
    # This rule is just an example; the certificate is valid for any subdomain
    - host: "foo.apps.example.com"
      http:
        #... backend configuration

```

### 4.3 Verification and Validation Workflow

To ensure the automation chain is functioning correctly or to debug issues, an
operator must be able to trace the issuance process step-by-step. This is done
by inspecting the custom resources that cert-manager creates.

1. **Check the **`Certificate`**:** This is the top-level resource representing
   the user's request. Its status provides a high-level overview of the process.

   ```bash
   kubectl describe certificate <cert-name> -n <namespace>
   ```

   A `Ready` condition with status `True` and an event
   `Certificate issued successfully` indicates success.[^22]

2. **Check the **`CertificateRequest`**:** This resource represents a single
   attempt to obtain a certificate. A new one is created for each issuance or
   renewal.

   ```bash
   kubectl get certificaterequest -n <namespace>
   ```

3. **Check the **`Order`**:** For ACME issuers like Let's Encrypt, an `Order`
   resource is created to manage the ACME order process. It tracks the status
   of the required challenges.

   ```bash
   kubectl describe order <order-name> -n <namespace>
   ```

   The output will list the associated `Challenge` resources and their current
   state.[^23]

4. **Check the **`Challenge`**:** This is the most critical resource for
   debugging DNS-01 issues. It represents the specific ACME challenge (e.g.,
   creating a TXT record). Its events and status will contain detailed error
   messages from the webhook or the ACME server.

   ```bash
   kubectl describe challenge <challenge-name> -n <namespace>
   ```

   Messages such as `Presented the DNS01 challenge for domain…` or error
   messages indicating API failures are informative.[^23]

5. **Check the Webhook Logs:** The logs from the Namecheap webhook pod are the
   final source of truth for API interactions.

   ```bash
   kubectl logs -n cert-manager -l \
     app.kubernetes.io/name=cert-manager-webhook-namecheap,app.kubernetes.io/instance=cert-manager \
     -f
   ```

These logs will show if the webhook is receiving challenge requests from
cert-manager and the outcome of its API calls to Namecheap.

## Part 5: Operational Excellence and Mitigation Strategies

Deploying the system is the first step; ensuring its long-term reliability,
security, and maintainability requires adopting operational best practices and
architecting solutions to inherent platform limitations.

### 5.1 Security Hardening

- **RBAC and Pod Security:** The cert-manager components and the third-party
  webhook run with elevated privileges, as they need to create and modify
  resources like `Secrets` and `ValidatingWebhookConfigurations`. It is
  essential to review the `ClusterRole` and `Role` bindings installed by the
  Helm charts and ensure they adhere to the principle of least privilege.
  Applying Kubernetes Pod Security Standards (such as `baseline` or
  `restricted`) to the `cert-manager` namespace can further harden the
  deployments.
- **Network Policies:** A robust security posture involves restricting network
  traffic to the bare minimum required. Kubernetes `NetworkPolicy` resources
  should be deployed to control ingress and egress traffic for the
  `cert-manager` namespace. These policies should enforce rules such as:

  - Allowing ingress to the webhook Service only from the Kubernetes API server
    on TCP 443 (or the configured webhook Service port).[^24]
- Allowing egress from the controller and webhook pods only to the Kubernetes
  API server and the required external endpoints (Let's Encrypt API and
  Namecheap API on TCP port 443).
- **Issuer Strategy:** Strictly enforce the use of the `letsencrypt-staging`
  `ClusterIssuer` for all non-production namespaces and development work. This
  prevents accidental rate-limiting from the Let's Encrypt production API,
  which can disrupt certificate issuance for the entire cluster. Production
  certificates should only be requested upon promotion to a production
  environment.

### 5.2 Troubleshooting Common TLS Pitfalls

A systematic approach to troubleshooting is key to minimizing downtime. The
following table provides a guide for diagnosing common issues in the TLS
issuance pipeline.[^23]

<!-- markdownlint-disable MD013 -->

| Symptom                                                                       | Diagnostic Command(s)                                                                                                                                                                                                        | Likely Cause & Resolution                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Certificate` is stuck in `Issuing` state for a long time.                    | `kubectl describe certificate <cert-name>` `kubectl describe order <order-name>`                                                                                                                                             | **Stalled ACME Order:** The `Order` is likely waiting for a `Challenge` to complete. Use the `describe order` command to find the name of the pending `Challenge` resource and investigate it further.                                                                                                                                                                                                                                                                           |
| `Challenge` fails with DNS propagation error.                                 | `kubectl describe challenge <challenge-name>` `kubectl logs -n cert-manager -l app.kubernetes.io/name=cert-manager-webhook-namecheap,app.kubernetes.io/instance=cert-manager` `dig TXT _acme-challenge.example.com @8.8.8.8` | **Webhook API Failure:** Check the webhook logs for authentication errors (invalid credentials) or connection errors (IP not whitelisted). **Slow DNS Propagation:** The DNS provider may be slow to propagate the TXT record. Some webhooks allow configuring a longer propagation delay. **Incorrect Nameservers:** cert-manager's self-check may be failing. Consider configuring recursive nameservers for the controller via Helm values (`--dns01-recursive-nameservers`). |
| Webhook pod is in `CrashLoopBackOff`.                                         | `kubectl logs -n cert-manager <webhook-pod-name> --previous` `kubectl describe pod -n cert-manager <webhook-pod-name>`                                                                                                       | **Missing Secret:** The pod cannot find the Kubernetes secret containing the API credentials. Verify the secret exists in the correct namespace and its name matches the `ClusterIssuer` configuration. **RBAC Permissions:** The webhook's `ServiceAccount` may lack the necessary permissions to read secrets or interact with the Kubernetes API. Check the `ClusterRole` associated with it.                                                                                 |
| `kubectl` commands fail with `x509: certificate signed by unknown authority`. | `kubectl get apiservice v1.webhook.cert-manager.io`                                                                                                                                                                          | **Webhook Not Ready:** This is common immediately after installation. The cert-manager webhook needs time to generate its self-signed CA and inject it into the `APIService` resource. Wait a few minutes and retry. If it persists, the `cainjector` component may be failing.                                                                                                                                                                                                  |
<!-- markdownlint-enable MD013 -->

### 5.3 Advanced Architecture: Mitigating the IP Whitelisting Constraint

As established in Part 1, the Namecheap API's mandatory IP whitelisting is the
primary architectural hurdle for a production-ready system. The following
strategies provide robust solutions to this problem.

#### Strategy 1: Static Egress via NAT Gateway (The Infrastructure Approach)

- **Concept:** This strategy involves routing all outbound traffic from the
  DOKS cluster's worker nodes through a DigitalOcean NAT Gateway. A NAT Gateway
  has a static public IP address, which can then be safely added to the
  Namecheap API whitelist.
- **Implementation:** This is configured entirely at the infrastructure layer
  using OpenTofu. A custom `digitalocean_vpc` is created, and a
  `digitalocean_nat_gateway` is attached to it. The DOKS cluster is then
  provisioned within this custom VPC, ensuring all its egress traffic is routed
  through the gateway.
- **Analysis:** This is a clean and comprehensive solution. It solves the
  problem not only for the cert-manager webhook but for any other workload in
  the cluster that might require a static egress IP. However, it introduces
  additional infrastructure cost for the NAT Gateway and centralizes the egress
  point, which could be a performance or availability consideration.

#### Strategy 2: DNS Delegation (The Cloud-Native Approach)

- **Concept:** This more nuanced strategy avoids the need for a static IP
  altogether. It leverages the fact that the DNS-01 challenge only requires
  control over a specific TXT record: `_acme-challenge.example.com`. Instead of
  giving the Namecheap webhook control over the entire domain, authority for
  just this specific subdomain is delegated to a different, more API-friendly
  DNS provider that has native support in cert-manager (e.g., DigitalOcean DNS
  or Cloudflare).
- **Implementation:**

  1. **Create a DNS Zone:** In the secondary provider (e.g., DigitalOcean),
     create a DNS zone for `example.com`.
  2. **Delegate with NS Records:** In Namecheap, using the
     `namecheap_domain_records` OpenTofu resource, create `NS` (nameserver)
     records for the hostname `_acme-challenge`, pointing to the nameservers of
     the secondary provider.
  3. **Configure solvers on one issuer:** Define multiple `dns01` solvers on a
     single `ClusterIssuer`, using a `selector` (for example,
     `dnsZones: ["example.com"]`) to route challenges for
     `_acme-challenge.example.com` to the DigitalOcean solver.
  4. **Alternative:** Create two issuers and reference the intended issuer
     explicitly on each `Certificate`/Ingress via `cert-manager.io/cluster-issuer`.

    Example fragment in the issuer:

    ```yaml
    spec:
      acme:
        solvers:
          - dns01:
              webhook: { ... Namecheap ... }
          - selector:
              dnsZones:
                - example.com
            dns01:
              digitalocean:
                tokenSecretRef:
                  name: do-dns-credentials
                  key: token
    ```

- **Analysis:** This is an elegant, cloud-native solution. It has no additional
  infrastructure cost and aligns well with microservice principles by
  delegating specific responsibilities. It is more complex to configure
  initially but offers greater flexibility and avoids creating a centralized
  network dependency.

#### Strategy 3: Manual IP Whitelisting (The Non-Production Approach)

- **Concept:** This involves manually identifying the public IP address of the
  Kubernetes node where the webhook pod is currently running and adding that IP
  to the Namecheap whitelist.
- **Analysis:** This approach is fundamentally flawed for any automated system.
  It is brittle, requires constant manual intervention, and will inevitably
  lead to outages when nodes are recycled. It should only be considered as a
  temporary method for initial testing or debugging and is completely
  unsuitable for production.

The following table provides a strategic comparison of these mitigation
approaches.

<!-- markdownlint-disable MD013 -->

| Strategy                | Implementation Complexity                                                     | Ongoing Cost                                  | Operational Overhead                                        | Reliability/Scalability                                      | Recommendation                                                                          |
| ----------------------- | ----------------------------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| **NAT Gateway**         | Medium (Requires VPC and NAT Gateway configuration in OpenTofu)               | Moderate (Recurring cost for the NAT Gateway) | Low (Set-and-forget once configured)                        | High (Reliable and scales with the cluster)                  | **Viable.** Best if a static egress IP is needed for other cluster services.            |
| **DNS Delegation**      | High (Requires managing two DNS providers and complex cert-manager selectors) | Low (No additional infrastructure cost)       | Low (Set-and-forget once configured)                        | Very High (Most flexible and resilient cloud-native pattern) | **Highly Recommended.** The superior architectural choice for a dedicated TLS solution. |
| **Manual Whitelisting** | Low (Manual UI interaction)                                                   | None                                          | Very High (Constant monitoring and manual updates required) | Very Low (Guaranteed to fail in a dynamic environment)       | **Not Recommended.** Unsuitable for production or any automated workflow.               |

<!-- markdownlint-enable MD013 -->
## Conclusion: Achieving a Fully Automated, Secure Application Endpoint

The architecture detailed in this report successfully extends the principles of
the GitOps-driven DNS solution to create a comprehensive, declarative, and
fully automated system for managing the entire TLS lifecycle in a DigitalOcean
Kubernetes environment. By integrating OpenTofu for foundational
infrastructure, FluxCD as the GitOps reconciler, and cert-manager with a
specialized webhook, this solution transforms certificate management from a
manual, error-prone task into a seamless, reliable, and secure workflow.

The primary benefits of this integrated approach are a direct reflection of the
core tenets of GitOps:

- **Velocity:** Developer teams are empowered to secure their applications
  through self-service, using familiar tools like Git and Kubernetes manifests.
  This eliminates the operational bottleneck of filing tickets for certificate
  creation, drastically reducing the time from code commit to a secure,
  publicly available endpoint.
- **Reliability:** The declarative model, enforced by the continuous
  reconciliation loops of FluxCD and cert-manager, creates a self-healing
  system. Any configuration drift or manual out-of-band changes are
  automatically corrected to match the desired state defined in Git, leading to
  a highly predictable and stable platform.
- **Security:** The security posture is enhanced at multiple levels. Sensitive
  API credentials are encrypted end-to-end using Mozilla SOPS, removing them
  from plain text exposure. The entire history of changes is captured in an
  immutable Git log, providing a clear audit trail and enabling peer review for
  all modifications to the TLS configuration.
- **Consistency:** With Git as the single source of truth, the state of TLS
  certificates in the cluster is always consistent with the application
  definitions. This eliminates configuration drift and provides a single,
  unified view of the system's desired state.

However, a truly expert implementation must confront and solve real-world
constraints. The most significant challenge identified in this specific
technology stack is the Namecheap API's mandatory static IP whitelisting, a
requirement fundamentally at odds with the dynamic nature of cloud-native
infrastructure. While a NAT Gateway offers a viable infrastructure-level
solution, the final and strongest recommendation is to adopt the **DNS
Delegation strategy**. By delegating authority for the `_acme-challenge`
subdomain to a more API-centric provider like DigitalOcean DNS, the system can
leverage a native, fully-supported cert-manager solver. This approach is more
cost-effective, aligns better with cloud-native design patterns of delegating
responsibility, and provides the highest degree of flexibility and resilience
for a production environment. By implementing this strategy, the organization
can achieve a truly automated, secure, and operationally excellent application
delivery platform.

[^1]: Kubernetes Dynamic DNS With Cloudflare — Cloudflare Blog, accessed on 1
      September 2025,
<https://blog.cloudflare.com/kubernetes-dynamic-dns-with-cloudflare/>

[^2]: cert-manager/cert-manager: Automatically provision and manage TLS
   certificates in Kubernetes — GitHub, accessed on 1 September 2025,
   [https://github.com/cert-manager/cert-manager](https://github.com/cert-manager/cert-manager)

[^3]: Providers — OpenTofu, accessed on 1 September 2025,
   [https://opentofu.org/docs/language/providers/](https://opentofu.org/docs/language/providers/)

[^4]: Provider: DigitalOcean — OpenTofu Registry, accessed on 1 September 2025,
   <https://registry.opentofu.org/providers/opentofu/digitalocean/latest>

[^5]: digitalocean_kubernetes_cluster | Resources | digitalocean …, accessed on
   1 September 2025,
   [https://docs.digitalocean.com/reference/terraform/reference/resources/kubernetes_cluster/](https://docs.digitalocean.com/reference/terraform/reference/resources/kubernetes_cluster/)

[^6]: Namecheap Terraform Provider — Domains, accessed on 1 September 2025,
   [https://www.namecheap.com/support/knowledgebase/article.aspx/10502/2208/namecheap-terraform-provider/](https://www.namecheap.com/support/knowledgebase/article.aspx/10502/2208/namecheap-terraform-provider/)

[^7]: Obtaining an API key from Namecheap | Yunohost, accessed on 1 September
    2025,
    [https://doc.yunohost.org/admin/get_started/providers/registrar/namecheap/](https://doc.yunohost.org/admin/get_started/providers/registrar/namecheap/)

[^8]: Namecheap API introduction, accessed on 1 September 2025,
    <https://www.namecheap.com/support/api/intro/>

[^9]: Enable Dynamic DNS for your domain — Namecheap Knowledgebase, accessed on
      1 September 2025,
    <https://www.namecheap.com/support/knowledgebase/article.aspx/29/11/enable-dynamic-dns>

[^10]: namecheap_domain_records | resources | namecheap/namecheap | Providers |
    OpenTofu and Terraform Registry — [Library.tf](http://Library.tf), accessed
    on 1 September 2025,
    [https://library.tf/providers/namecheap/namecheap/latest/docs/resources/domain_records](https://library.tf/providers/namecheap/namecheap/latest/docs/resources/domain_records)

[^11]: Manage Kubernetes secrets with SOPS | Flux — Flux CD, accessed on 1
    September 2025,
    [https://fluxcd.io/flux/guides/mozilla-sops/](https://fluxcd.io/flux/guides/mozilla-sops/)

[^12]: Setting Up Flux CD in a Kubernetes Cluster with SOPS Encryption. —
       Medium,
    accessed on 1 September 2025,
    [https://medium.com/@deepakraajesh/setting-up-flux-cd-in-a-kubernetes-cluster-with-sops-encryption-bd72b2d0e468](https://medium.com/@deepakraajesh/setting-up-flux-cd-in-a-kubernetes-cluster-with-sops-encryption-bd72b2d0e468)

[^13]: Manage Helm Releases — Flux CD, accessed on 1 September 2025,
    [https://fluxcd.io/flux/guides/helmreleases/](https://fluxcd.io/flux/guides/helmreleases/)

[^14]: Helm — cert-manager Documentation, accessed on 1 September 2025,
    [https://cert-manager.io/docs/installation/helm/](https://cert-manager.io/docs/installation/helm/)

[^15]: cert-manager 1.18.2 — Artifact Hub, accessed on 1 September 2025,
    [https://artifacthub.io/packages/helm/cert-manager/cert-manager](https://artifacthub.io/packages/helm/cert-manager/cert-manager)

[^16]: Webhook — cert-manager Documentation, accessed on 1 September 2025,
    [https://cert-manager.io/docs/configuration/acme/dns01/webhook/](https://cert-manager.io/docs/configuration/acme/dns01/webhook/)

[^17]: jamesgoodhouse/cert-manager-webhook-namecheap: A … — GitHub, accessed on
    1 September 2025,
    [https://github.com/jamesgoodhouse/cert-manager-webhook-namecheap](https://github.com/jamesgoodhouse/cert-manager-webhook-namecheap)

[^18]: Issuer Configuration — cert-manager Documentation, accessed on 1
       September
    2025,
    [https://cert-manager.io/docs/configuration/](https://cert-manager.io/docs/configuration/)

[^19]: DNS01 — cert-manager Documentation, accessed on 1 September 2025,
    [https://cert-manager.io/docs/configuration/acme/dns01/](https://cert-manager.io/docs/configuration/acme/dns01/)

[^20]: Certificate resource — cert-manager Documentation, accessed on 1
       September
    2025,
    [https://cert-manager.io/docs/usage/certificate/](https://cert-manager.io/docs/usage/certificate/)

[^21]: DNS Domain Validation (dns-01) | Certify The Web Docs, accessed on 1
    September 2025,
    [https://docs.certifytheweb.com/docs/dns/validation/](https://docs.certifytheweb.com/docs/dns/validation/)

[^22]: Verifying the Installation — cert-manager Documentation, accessed on 1
    September 2025,
    [https://cert-manager.io/v1.6-docs/installation/verify/](https://cert-manager.io/v1.6-docs/installation/verify/)

[^23]: Troubleshooting Issuing ACME Certificates — cert-manager Documentation,
    accessed on 1 September 2025,
    [https://cert-manager.io/v1.0-docs/faq/acme/](https://cert-manager.io/v1.0-docs/faq/acme/)
[^24]: Best Practice — cert-manager Documentation, accessed on 1 September 2025,
    [https://cert-manager.io/docs/installation/best-practice/](https://cert-manager.io/docs/installation/best-practice/)
