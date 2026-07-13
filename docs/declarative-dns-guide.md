# Declarative DNS: A Comprehensive Guide to Automating Cloudflare DNS in Kubernetes with FluxCD, ExternalDNS, and OpenTofu

## Part 1: The Architectural Blueprint for Modern DNS Automation

### 1.1 Introduction: The DNS Dilemma in Dynamic Environments

In modern cloud-native ecosystems, particularly those orchestrated by
Kubernetes, the lifecycle of applications is inherently dynamic and ephemeral.
Services are created, scaled, and destroyed in response to demand, a process
that renders traditional, static infrastructure management practices untenable.
A significant point of friction in this model is Domain Name System (DNS)
management. The conventional workflow often involves a developer deploying an
application, determining its external IP address, and then filing a ticket or
creating a pull request against a separate infrastructure repository to have a
DNS record created or updated. This manual process is not only slow and
inefficient but is also a frequent source of human error, leading to
configuration drift and operational delays.[^1]

This manual approach represents a fundamental bottleneck, decoupling the
application’s lifecycle from its public discoverability. An application may be
ready to serve traffic within seconds, but it remains inaccessible until a
manual DNS update propagates. This operational paradigm is at odds with the
agility and automation that Kubernetes promises.[^1]

The solution lies in adopting a declarative, automated approach where DNS
management is a direct, synchronized reflection of the application state within
the cluster. This guide details an architectural blueprint for achieving this
state of “DNS-as-Code” by integrating a suite of powerful, open-source tools.
By leveraging the principles of GitOps, this architecture transforms DNS
management from a manual chore into a seamless, automated workflow. GitOps
establishes a Git repository as the single source of truth for the desired
state of the entire system. An automated agent, or operator, running within the
cluster ensures that the live state continuously converges to the state
declared in Git, making infrastructure management version-controlled,
auditable, and collaborative.[^2]

### 1.2 Synergistic Components of the Ecosystem

This automated DNS architecture is composed of five distinct but synergistic
components. The power of the system derives not from any single tool, but from
their carefully orchestrated interplay, where each component fulfils a
specific, well-defined role.

- **Kubernetes:** At the core of the ecosystem, Kubernetes serves as the
  container orchestration platform and the source of truth for application
  state. It manages the lifecycle of containerized workloads and provides the
  resource primitives—primarily `Services` and `Ingresses`—that define how
  applications are networked and exposed. In this architecture, Kubernetes
  resources become the declarative intent for public DNS records.[^3]
- **Cloudflare:** As the authoritative DNS provider and network edge,
  Cloudflare is the system’s “actuality” layer. It is responsible for resolving
  public DNS queries and, optionally, for providing security and performance
  services like DDoS mitigation and a Content Delivery Network (CDN) through
  its proxy feature. Its comprehensive REST API is the critical programmatic
  interface that enables external automation.[^4]
- **ExternalDNS:** This component is the crucial bridge between the Kubernetes
  cluster’s internal state and the external DNS provider. ExternalDNS runs as a
  controller within the cluster, continuously watching the Kubernetes API for
  specific resources (like `Ingresses` and `Services`) that have been annotated
  for DNS management. Upon detecting a change, it translates the resource’s
  specifications into the appropriate API calls to configure records in
  Cloudflare, effectively making Kubernetes resources discoverable via public
  DNS servers.[^3]
- **FluxCD:** FluxCD is the GitOps operator that automates the entire cluster
  management lifecycle. Its role extends beyond simple application deployment;
  it manages the desired state of all Kubernetes resources declaratively from a
  Git repository. This includes the deployment, configuration, and lifecycle
  management of the ExternalDNS controller itself. FluxCD ensures that the
  state of the cluster—including the tools that manage its external
  integrations—perfectly mirrors the configuration defined in Git.[^1]
- **OpenTofu:** As a leading Infrastructure as Code (IaC) tool, OpenTofu is
  responsible for provisioning and managing the foundational, long-lived
  infrastructure components. In this architecture, its role is specifically to
  manage the Cloudflare DNS zone itself (e.g., `example.com`). This task is
  typically performed once or infrequently, establishing a clear separation
  between the stable, underlying infrastructure and the dynamic,
  application-driven records managed by ExternalDNS.[^5]

This layered architecture establishes a powerful separation of concerns. The
management of static, foundational infrastructure (the DNS zone) is handled by
a dedicated IaC tool suited for deliberate, planned changes. The management of
the in-cluster tooling (ExternalDNS) is handled by a GitOps operator that
ensures declarative state synchronization. Finally, the management of dynamic,
ephemeral application DNS records is delegated to a specialized controller that
reacts in real-time to the application lifecycle. This decoupling is a
significant architectural advantage that enhances both operational stability
and development velocity.

| Component       | Primary Role                | Scope of Control                                                                | Managed By                             |
| --------------- | --------------------------- | ------------------------------------------------------------------------------- | -------------------------------------- |
| **Kubernetes**  | Application Orchestration   | Manages the lifecycle of containers, Pods, Services, and Ingresses.             | Platform/Application Teams             |
| **Cloudflare**  | Authoritative DNS Provider  | Hosts and resolves public DNS records; provides edge network services.          | OpenTofu (Zone), ExternalDNS (Records) |
| **ExternalDNS** | DNS Automation Controller   | Translates Kubernetes resources into Cloudflare DNS records.                    | FluxCD                                 |
| **FluxCD**      | GitOps Operator             | Synchronizes the entire Kubernetes cluster state with a Git repository.         | Platform Team                          |
| **OpenTofu**    | Infrastructure as Code Tool | Provisions and manages the foundational Cloudflare DNS zone and static records. | Platform Team                          |

### 1.3 The End-to-End Data and Control Flow

The complete automated workflow, from a developer’s code commit to a publicly
resolvable DNS record, follows a precise and auditable sequence of events
orchestrated by the integrated components:

1. **Intent Declaration:** A developer defines a new application to be exposed
   publicly. They create a standard Kubernetes `Ingress` manifest, which
   specifies routing rules. Critically, they add specific annotations to this
   manifest, such as
   `external-dns.alpha.kubernetes.io/hostname: my-app.example.com`, to declare
   the desired public DNS name.[^6]
2. **Commit to Source of Truth:** The developer commits this `Ingress` manifest
   to a designated application configuration path within the GitOps repository
   and pushes the change.
3. **Git Repository Reconciliation:** FluxCD’s `source-controller`, which is
   configured to monitor the Git repository, detects the new commit within its
   configured interval.[^7] It fetches the latest revision and stores it as an
   artifact within the cluster.
4. **Cluster State Synchronization:** FluxCD’s `kustomize-controller`, which is
   subscribed to changes from the `source-controller`, detects the new
   artifact. It applies the `Ingress` manifest to the Kubernetes cluster,
   creating the Ingress resource via the Kubernetes API server.[^7]
5. **DNS Controller Detection:** The ExternalDNS controller, which is
   continuously watching the Kubernetes API for changes to `Ingress` resources,
   detects the creation of the new `Ingress`.[^8]
6. **API-driven DNS Configuration:** ExternalDNS parses the annotations on the
   `Ingress` resource. It extracts the desired hostname (`my-app.example.com`)
   and identifies the target IP address from the `Ingress` object’s status
   field (which is populated by the ingress controller). Using the securely
   stored Cloudflare API token, ExternalDNS makes a series of API calls to
   Cloudflare to create the corresponding `A` or `CNAME` record, along with a
   `TXT` record for ownership verification.[^1]
7. **Public Resolution:** The DNS record is now active in Cloudflare’s global
   network. Public DNS queries for `my-app.example.com` resolve to the IP
   address of the cluster’s ingress controller, which in turn routes traffic to
   the newly deployed application. The entire process, from `git push` to a
   live endpoint, is completed automatically without any manual intervention.

## Part 2: Phase I - Foundational Infrastructure Setup

Before deploying the automated DNS system, a foundational environment must be
established. This phase involves installing the necessary command-line tools,
preparing the Cloudflare account, and bootstrapping the FluxCD GitOps engine
onto the Kubernetes cluster.

### 2.1 Prerequisites and Tooling Installation

A successful implementation requires a specific set of tools and accounts. The
following checklist outlines the necessary components:

- **Kubernetes Cluster:** A running Kubernetes cluster is required. For local
  development and testing, tools like `kind` are suitable. For production, a
  managed Kubernetes service such as GKE, EKS, or AKS is recommended.[^9]
- **Cloudflare Account:** An active Cloudflare account is necessary, with a
  domain already registered and onboarded.[^9]
- **Git Provider Account:** A Git repository hosted on a provider like GitHub,
  GitLab, or Gitea is required to serve as the single source of truth for the
  GitOps workflow.[^10]
- **Command-Line Tools:** The following CLI tools must be installed on the
  local administrative machine:
- **kubectl:** The Kubernetes command-line tool for interacting with the
  cluster API.
- **flux:** The CLI for bootstrapping and interacting with FluxCD.[^10]
- **tofu:** The OpenTofu CLI for managing infrastructure as code.[^5]
- **helm:** The Helm package manager CLI, useful for inspecting charts and
  templating values.[^9]

Installation instructions for these tools are widely available in their
official documentation. For example, the Flux CLI can be installed on Linux and
macOS using a simple shell script.[^10]

### 2.2 Configuring the Cloudflare Environment

Proper configuration of Cloudflare is a critical prerequisite. This involves
ensuring Cloudflare is the authoritative DNS provider for the domain and
generating a securely scoped API token for ExternalDNS.

#### 2.2.1 Domain Onboarding

Before any automation can occur, the domain must be fully managed by
Cloudflare. This is achieved by:

1. Adding the site (e.g., `example.com`) to the Cloudflare dashboard.
2. Updating the domain’s nameserver (NS) records at the domain registrar to
   point to the nameservers provided by Cloudflare.

This change delegates DNS authority for the domain to Cloudflare, allowing its
API to manage DNS records effectively.[^11]

#### 2.2.2 Generating a Scoped API Token

For security, it is imperative to use a narrowly-scoped API Token rather than
the legacy Global API Key. API tokens adhere to the principle of least
privilege, granting only the permissions necessary for a specific task.[^4]

To create a token for ExternalDNS:

1. Log in to the Cloudflare dashboard and navigate to “My Profile” -> “API
   Tokens”.

2. Click “Create Token” and select a custom token template.

3. Configure the token with the following exact permissions:

   - `Zone` -> `Zone` -> `Read`: Allows ExternalDNS to list and read details of
     the DNS zones in the account.
   - `Zone` -> `DNS` -> `Edit`: Allows ExternalDNS to create, update, and delete
     DNS records within a zone.

4. Under “Zone Resources,” scope the token to the specific zone(s) that will be
   managed by this Kubernetes cluster (e.g., `Include` -> `Specific zone` ->
   `example.com`). This prevents the token from being able to modify other
   domains in the account.

5. Create the token and securely copy the generated value. It will only be
   displayed once.[^1]

#### 2.2.3 Storing the API Token in Kubernetes

The generated API token must be stored securely within the Kubernetes cluster
for ExternalDNS to use. The standard method is to use a Kubernetes `Secret`.

Execute the following command, replacing `<CF_API_TOKEN>` with the token copied
from Cloudflare and `<NAMESPACE>` with the namespace where ExternalDNS will be
deployed (e.g., `external-dns`):

```bash
kubectl create secret generic cloudflare-api-token \
  --from-literal=apiToken=<CF_API_TOKEN> \
  -n <NAMESPACE>

```

It is crucial to note that the key used in the `--from-literal` flag (in this
case, `apiToken`) must match the key expected by the ExternalDNS Helm chart in
its values configuration. Some charts may expect `apiKey` or
`cloudflare_api_token`. Mismatched keys are a common source of authentication
failures.[^1]

### 2.3 Bootstrapping the GitOps Engine with FluxCD

With the prerequisites in place, the next step is to install FluxCD on the
cluster and link it to the GitOps repository. The `flux bootstrap` command
automates this entire process.[^10]

The bootstrap command installs the FluxCD controllers into the `flux-system`
namespace and commits their manifests to the specified Git repository. It also
configures a deploy key to allow the cluster to pull subsequent changes.

Example command for GitHub:

```bash
export GITHUB_USER="<github-username>"
export GITHUB_TOKEN="<github-pat>"

flux bootstrap github \
  --owner=$GITHUB_USER \
  --repository=my-gitops-repo \
  --branch=main \
  --path=./clusters/production \
  --personal

```

This command will create a private repository named `my-gitops-repo` under the
specified user’s account and configure Flux to monitor the
`clusters/production` directory within that repository.[^7]

The choice of authentication method between Flux and the Git provider—either a
Personal Access Token (PAT) via HTTPS or an SSH deploy key—has important
downstream consequences. While a PAT is straightforward, an SSH key is
generally more secure as it can be scoped to a single repository. By default,
`flux bootstrap` creates a read-only SSH deploy key. However, if advanced
features like Flux’s image update automation are planned, which require Flux to
commit changes back to the repository, a read-write key is necessary. This can
be enabled during bootstrap by adding the `--read-write-key=true` flag. Making
this decision upfront prevents the need to re-bootstrap or manually reconfigure
credentials later, ensuring the system is architected for full-cycle automation
from the start.[^12]

Upon successful bootstrap, the Git repository will contain a directory
structure similar to `clusters/production/flux-system/`, which holds the
declarative state of the FluxCD installation itself. All subsequent cluster
configurations, including the deployment of ExternalDNS, will be managed by
adding YAML manifests to this repository.[^13]

## Part 3: Phase II - Deploying and Configuring ExternalDNS via GitOps

With FluxCD acting as the GitOps engine, the deployment of ExternalDNS is no
longer an imperative `helm install` command but a declarative process. By
defining `HelmRepository` and `HelmRelease` custom resources in the Git
repository, FluxCD will automatically manage the lifecycle of the ExternalDNS
controller.

### 3.1 Defining the Helm Chart Source

The first step is to inform FluxCD where to find the ExternalDNS Helm chart.
This is accomplished by creating a `HelmRepository` resource. This manifest
tells Flux’s `source-controller` to periodically fetch the index from a
specified Helm repository URL and make its charts available as artifacts within
the cluster.[^3]

Create a file in the GitOps repository (e.g.,
`infrastructure/sources/helm-repositories.yaml`) with the following content:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: external-dns
  namespace: flux-system
spec:
  interval: 1h
  url: https://kubernetes-sigs.github.io/external-dns/

```

Once this file is committed and pushed, FluxCD will apply it, making the charts
from the `kubernetes-sigs` repository available for `HelmRelease` resources.
The `bitnami` repository is another common source for the ExternalDNS chart.[^3]

### 3.2 Crafting the ExternalDNS HelmRelease

The `HelmRelease` is the core declarative manifest for a Helm deployment
managed by FluxCD. It specifies the source chart, version, release name, and
configuration values.[^3] This single YAML file encapsulates the entire desired
state of the ExternalDNS deployment.

Create a file in the GitOps repository (e.g.,
`infrastructure/controllers/external-dns.yaml`) with the following
comprehensive configuration:

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: external-dns
  namespace: external-dns # Deploys to the 'external-dns' namespace
spec:
  interval: 15m
  chart:
    spec:
      chart: external-dns
      version: "1.14.x" # Pin to a minor version for stable updates
      sourceRef:
        kind: HelmRepository
        name: external-dns
        namespace: flux-system
      interval: 15m
  install:
    remediation:
      retries: 3
  upgrade:
    remediation:
      retries: 3
  releaseName: external-dns
  targetNamespace: external-dns
  values:
    crd:
      create: true
    # -- Role-Based Access Control (RBAC) configuration --
    rbac:
      create: true

    # -- DNS Provider Configuration --
    provider: cloudflare

    # -- Cloudflare Specific Settings --
    cloudflare:
      # Reference the secret containing the API token
      secretName: cloudflare-api-token
      # The key within the secret that holds the token value
      secretKey: apiToken

      # -- Core ExternalDNS behaviour --
    policy: sync # Allows create, update, and delete operations

    # -- Scoping and Ownership --
    domainFilters:
      - "example.com" # Restrict management to this domain

    txtOwnerId: "production-cluster-01" # Unique ID for this instance

    # -- Additional Arguments for Fine-Tuning --
    extraArgs:
      - --cloudflare-proxied=true # Enable Cloudflare proxy by default
      - --cloudflare-dns-records-per-page=5000 # Mitigate API rate limits

```

This `HelmRelease` manifest contains several critical configuration points:

- **Chart Specification:** It references the `external-dns` `HelmRepository`
  and specifies a semantic version range (`1.14.x`), allowing FluxCD to
  automatically apply patch updates while preventing breaking changes from
  major version upgrades.[^3]
- **Values Configuration:**
- `provider: cloudflare`: Explicitly sets Cloudflare as the DNS provider.[^14]
- `cloudflare.secretName`: Points to the Kubernetes `Secret` created in Phase
  I, decoupling the sensitive token from the declarative configuration.[^3]
- `domainFilters`: This is a crucial security and safety feature. It constrains
  the controller to only manage records within the specified domains,
  preventing it from accidentally modifying records in other zones.[^8]
  - `policy: sync`: This setting authorizes ExternalDNS to perform create,
    update, and delete operations. The alternative, `upsert-only`, would not
    remove DNS records when the corresponding Kubernetes resource is deleted,
    leading to stale and potentially insecure records.[^15]
- `extraArgs`: This array allows for passing command-line arguments directly to
  the ExternalDNS container. Here, it is used to enable the Cloudflare proxy by
  default and to configure a high records-per-page value to avoid hitting
  Cloudflare’s API rate limits.[^4]
- `txtOwnerId`: This is arguably the most important setting for operating
  ExternalDNS safely in any environment that is not trivially simple. When set,
  ExternalDNS creates an accompanying `TXT` record for every `A` or `CNAME`
  record it manages. This `TXT` record contains the owner ID. Before modifying
  or deleting any DNS record, ExternalDNS first verifies the presence of this
  ownership record and checks if the ID matches its own. This mechanism is
  fundamental for enabling safe, multi-tenant operation. For instance, staging
  and production clusters can manage subdomains within the same Cloudflare zone
  without interfering with each other, as each instance will only touch records
  that it verifiably “owns.” Without a unique `txtOwnerId` for each instance,
  one controller could mistakenly delete records managed by another, leading to
  outages.[^1]

Committing this `HelmRelease` manifest to the Git repository triggers FluxCD to
deploy and configure ExternalDNS according to these exact specifications,
establishing a fully declarative, version-controlled management plane for the
DNS controller itself.

## Part 4: Phase III - Dynamic Subdomain Management in Action

With ExternalDNS deployed and configured via GitOps, the system is ready to
automate the creation of DNS records based on Kubernetes resources. This
section demonstrates the primary workflow using Ingress annotations and
explores the `DNSEndpoint` CRD as a powerful alternative.

### 4.1 Automating DNS with Kubernetes Ingress Annotations

The most common method for exposing web services in Kubernetes is through an
`Ingress` resource. ExternalDNS leverages annotations on these resources to
trigger DNS automation.

First, a sample application is deployed. The following manifests define a
simple Nginx deployment and a `ClusterIP` service to expose it internally.[^9]

**Sample Application Manifest (**`nginx-app.yaml`**):**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.25.5
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
  namespace: default
spec:
  selector:
    app: nginx
  ports:
    - protocol: TCP
      port: 80
      targetPort: 80

```

Next, an `Ingress` resource is created to expose this service externally. This
manifest contains the critical annotations that ExternalDNS will act upon.

**Ingress Manifest (**`nginx-ingress.yaml`**):**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nginx-ingress
  namespace: default
  annotations:
    # --- ExternalDNS Annotations ---
    # Specifies the desired DNS hostname. This is the primary trigger.
    external-dns.alpha.kubernetes.io/hostname: nginx.example.com

    # Overrides the default proxy setting for this specific record.
    external-dns.alpha.kubernetes.io/cloudflare-proxied: "true"

    # Sets a custom Time-To-Live (TTL) for the DNS record in seconds.
    external-dns.alpha.kubernetes.io/ttl: "120"
spec:
  ingressClassName: nginx # Assumes an NGINX Ingress Controller is installed
  rules:
  - host: "nginx.example.com"
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: nginx-service
            port:
              number: 80

```

**Deep Dive into Annotations:**

- `external-dns.alpha.kubernetes.io/hostname`: This is the essential annotation
  that signals to ExternalDNS that this `Ingress` should have a corresponding
  DNS record created. The value specifies the fully qualified domain name
  (FQDN).[^6]
- `external-dns.alpha.kubernetes.io/cloudflare-proxied`: This annotation
  provides granular, per-resource control over Cloudflare’s proxy feature (the
  “orange cloud”). By setting it to `"true"` (as a string), this specific
  record will be proxied, regardless of the default setting in the
  `HelmRelease`. This empowers application developers to control network
  features like CDN and WAF directly from their application manifests, a
  powerful example of “shifting left” infrastructure control.[^16]
- `external-dns.alpha.kubernetes.io/ttl`: This allows for setting a custom TTL
  for the DNS record, overriding any provider defaults.[^17]

When these manifests are committed to the GitOps repository, FluxCD applies
them. ExternalDNS detects the new `Ingress` with the `hostname` annotation and
proceeds to create the `nginx.example.com` `A` record in Cloudflare, pointing
to the external IP address of the cluster’s ingress controller.

### 4.2 An Alternative Approach: The DNSEndpoint CRD

While `Ingress` resources are ideal for HTTP/S services, there are scenarios
where DNS records are needed for other purposes, such as pointing a domain to a
specific IP address not managed by an `Ingress`, or for non-HTTP services. For
these cases, ExternalDNS provides a `DNSEndpoint` Custom Resource Definition
(CRD).[^3]

To use this feature, the CRD must first be enabled in the ExternalDNS
`HelmRelease` by setting `crd.create: true` in the `values` section.[^3]

Once enabled, a `DNSEndpoint` resource can be created to define a DNS record
declaratively:

**DNSEndpoint Manifest (**`custom-record.yaml`**):**

```yaml
apiVersion: externaldns.k8s.io/v1alpha1
kind: DNSEndpoint
metadata:
  name: static-entry
  namespace: default
spec:
  endpoints:
    - dnsName: static.example.com
      recordType: A
      recordTTL: 300
      targets:
        - "192.0.2.100"

```

This manifest instructs ExternalDNS to create an `A` record for
`static.example.com` pointing to the IP address `192.0.2.100`. This provides a
flexible, Kubernetes-native way to manage any DNS record declaratively through
the same GitOps workflow.[^3]

### 4.3 Verification and Validation Workflow

After committing changes to the Git repository, it is essential to verify that
the entire automation chain has executed successfully. This involves checking
the status of each component in the workflow.

1. **Verify FluxCD Reconciliation:** Check the status of the FluxCD
   `Kustomization` and `HelmRelease` to ensure the manifests have been
   successfully applied to the cluster.

   ```bash
   # Check the status of all Kustomizations, watch for updates
   flux get kustomizations --watch

   # Force reconciliation to ensure the latest manifests are applied
   flux reconcile kustomization external-dns -n flux-system --with-source

   # Check the status of the ExternalDNS HelmRelease
   flux get helmrelease external-dns -n external-dns

   # Inspect the resulting Ingress resource
   kubectl get ingress nginx-ingress -n default -o wide
   ```

   A `READY` status of `True` indicates success.[^18]

2. **Inspect ExternalDNS Logs:** The logs of the ExternalDNS pod are the
   primary source for debugging its behaviour. They will show whether it has
   detected the new resource and what actions it is taking with the Cloudflare
   API.

   ```bash
   # Tail the logs of the ExternalDNS pod(s)
   kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -f
   ```

   Look for log entries mentioning the creation or update of the desired DNS
   record.[^19]

3. **Check Cloudflare dashboard:** Log in to the Cloudflare dashboard and
   navigate to the DNS records page for the domain. Verify that the new `A` or
   `CNAME` record has been created, along with its corresponding `TXT`
   ownership record.

4. **Confirm public DNS resolution:** A command-line tool such as `dig` can
   query a well-known public DNS resolver to confirm that the record resolves
   to the expected IP address.

```bash
# Query for the A record
dig A nginx.example.com @1.1.1.1 +short

```

The command should return the external IP address of the Kubernetes cluster's
Ingress Controller.[^20]

## Part 5: Managing Foundational DNS with OpenTofu

While ExternalDNS excels at managing dynamic, application-level DNS records,
the foundational DNS zone itself and its static, long-lived records are best
managed using a dedicated Infrastructure as Code (IaC) tool like OpenTofu. This
creates a clear and robust separation of concerns, aligning the management tool
with the lifecycle of the resource.

### 5.1 Configuring the OpenTofu Cloudflare Provider

To manage Cloudflare resources with OpenTofu, the official Cloudflare provider
must be configured. This involves declaring the provider in the OpenTofu
configuration and supplying the necessary credentials.

Create a file named `providers.tf` with the following content:

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "opentofu/cloudflare"
      version = "~> 4.0"
    }
  }
}

# Configure the Cloudflare Provider
# It is strongly recommended to use environment variables for credentials
# export CLOUDFLARE_API_TOKEN="<your-api-token>"
provider "cloudflare" {
  # api_token can be set here, but environment variable is preferred
}

```

This configuration specifies the Cloudflare provider and its version.
Authentication is handled automatically if the `CLOUDFLARE_API_TOKEN`
environment variable is set, which is the most secure method as it avoids
hardcoding secrets in version-controlled files.[^5]

### 5.2 Managing the Cloudflare Zone as Code

With the provider configured, the Cloudflare zone can be defined as an OpenTofu
resource. The `cloudflare_zone` resource manages the lifecycle of the DNS zone
itself.

Create a file named `main.tf` to define the zone and any static records:

```hcl
# Retrieve Cloudflare Account ID from a data source or variable
variable "cloudflare_account_id" {
  type        = string
  description = "The Account ID of your Cloudflare account."
}

# Manage the DNS Zone itself
resource "cloudflare_zone" "primary" {
  account_id = var.cloudflare_account_id
  zone       = "example.com"
  plan       = "free" # Or "pro", "business", etc.
}

# Manage a static MX record for email
resource "cloudflare_record" "mx_google" {
  zone_id = cloudflare_zone.primary.id
  name    = "example.com"
  type    = "MX"
  value   = "aspmx.l.google.com"
  priority = 1
  ttl      = 3600
}

# Manage a static SPF record
resource "cloudflare_record" "spf" {
  zone_id = cloudflare_zone.primary.id
  name    = "example.com"
  type    = "TXT"
  value   = "v=spf1 include:_spf.google.com ~all"
  ttl     = 3600
}

```

This OpenTofu code declaratively manages the existence of the `example.com`
zone and ensures that essential static records, such as those for email (MX,
SPF), are always present and correctly configured.[^11]

### 5.3 Defining Responsibilities: OpenTofu vs. ExternalDNS

The combination of OpenTofu and ExternalDNS creates a powerful, two-tiered
management system that aligns with the different operational cadences and
responsibilities within a modern engineering organization.

- **OpenTofu’s Responsibility (The Platform Layer):** OpenTofu is used by the
  Platform or Infrastructure team to manage the core, stable infrastructure.
  Its scope includes:
- The lifecycle of the Cloudflare DNS zone (`cloudflare_zone`).
- Static, global DNS records that are not tied to specific Kubernetes
  workloads. This includes apex records (`@`), `www` redirects, and
  email-related records (`MX`, `SPF`, `DKIM`, `DMARC`).[^11]
- Changes at this layer are typically infrequent, critical, and subject to a
  rigorous review process, for which OpenTofu’s `plan` and `apply` workflow is
  perfectly suited.
- **ExternalDNS’s Responsibility (The Application Layer):** ExternalDNS is used
  by Application development teams (via the GitOps workflow) to manage dynamic,
  ephemeral DNS records. Its scope is strictly limited to:
- `A` and `CNAME` records for services and applications deployed within the
  Kubernetes cluster.
- The lifecycle of these records is directly tied to the lifecycle of the
  corresponding Kubernetes `Ingress` or `Service` resource.[^8]
- Changes at this layer are frequent, automated, and self-service, enabling
  high development velocity.

This clear demarcation prevents tooling conflicts and organizational
bottlenecks. The platform team provides a stable foundation (the zone) and a
safe, automated tool (ExternalDNS, constrained by `domainFilters` and
`txtOwnerId`). Application teams can then operate with autonomy within these
established guardrails, managing their own DNS needs as part of their standard
development workflow. This model is not just a technical architecture; it is an
effective organizational pattern that balances central control with delegated
authority, optimizing for both stability and agility.

## Part 6: Operational Excellence and Advanced Strategies

Implementing the automated DNS system is the first step. Ensuring its long-term
reliability, security, and maintainability requires attention to day-two
operational practices. This section covers security hardening, troubleshooting
common issues, and a comparative analysis of the GitOps approach against
traditional methods.

### 6.1 Security Hardening and Best Practices

A production-grade system must be built on a foundation of strong security
practices.

- **Git Repository Security:** The GitOps repository is the single source of
  truth for the cluster’s state. As such, it must be protected. Implementing
  branch protection rules is essential. For the main branch that reflects the
  production state, rules should be configured to require pull requests for all
  changes and mandate at least one review from a designated code owner. This
  enforces a four-eyes principle, ensuring that no single individual can push
  un-reviewed changes to the cluster, and creates a clear audit trail for every
  modification.[^2]
- **Encrypted Secret Management:** While Kubernetes Secrets are an improvement
  over plain text, their values are only Base64 encoded, not encrypted at rest
  within `etcd` by default. For a more robust security posture, secrets stored
  in the Git repository should be encrypted. FluxCD has native integration with
  Mozilla SOPS (Secrets OPerationS), which allows for encrypting YAML values
  using keys from cloud Key Management Service (KMS) systems (for example, AWS
  KMS, GCP KMS) or PGP keys. With SOPS, the `HelmRelease` can reference an
  encrypted secret, and Flux’s `kustomize-controller` will decrypt it
  on-the-fly just before applying it to the cluster. This ensures that
  sensitive data like the Cloudflare API token remains encrypted end-to-end,
  from the Git repository to the cluster.[^21]
- **API Rate Limiting:** Cloudflare imposes a global API rate limit of 1,200
  requests per five minutes for most accounts. In a large or highly dynamic
  cluster, a naive ExternalDNS configuration could easily exceed this limit,
  leading to failed DNS updates. To mitigate this, the
  `--cloudflare-dns-records-per-page` command-line argument should be set to a
  high value (e.g., 1000 or 5000) in the `HelmRelease`. This instructs
  ExternalDNS to fetch records from the Cloudflare API in larger batches,
  significantly reducing the total number of API calls required for
  reconciliation.[^4]

### 6.2 Troubleshooting Common Integration Pitfalls

Even in a well-architected system, issues can arise. A systematic approach to
troubleshooting is key to rapid resolution.

- Symptom: No DNS records are created

  - Verify:

    ```bash
    kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -f
    ```

  - Causes/Resolution:

    - Authentication error. Look for `Invalid request headers (6003)`.
      Ensure the API token has `Zone:Read` and `DNS:Edit` permissions.
      Re-create the Kubernetes secret, avoiding invisible characters and
      matching the expected secret key name (for example, `apiToken`).[^22]
    - RBAC error. Inspect logs for permission denied when reading `Ingress` or
      `Service` resources. Ensure the `HelmRelease` sets `rbac.create=true` and
      that the `ClusterRole` grants the required permissions.

- Symptom: Stale DNS records are not deleted

  - Verify: `kubectl get helmrelease external-dns -n external-dns -o yaml`
  - Causes/Resolution:
    - Incorrect policy. The `policy` in the `HelmRelease` must be `sync`. If it
      is `upsert-only`, ExternalDNS will not delete records.[^15]
    - Ownership mismatch. If `txtOwnerId` changed since records were created,
      ExternalDNS will no longer recognize them as its own and will not delete
      them.

- Symptom: Records created but not proxied (“grey cloud”)

  - Verify: `kubectl get ingress <ingress-name> -o yaml`
  - Causes/Resolution:
    - Missing annotation/argument. Either set the default behaviour with
      `--cloudflare-proxied=true` in `extraArgs` in the `HelmRelease`, or add
      the annotation
      `external-dns.alpha.kubernetes.io/cloudflare-proxied: "true"` (string) to
      the relevant `Ingress` manifest.[^16]

- Symptom: Flux Kustomization is not ready

  - Verify: `flux get kustomizations <name>` and
    `kubectl describe kustomization <name>`
  - Causes/Resolution:
    - Source not ready. Check the `GitRepository` or `HelmRepository` status via
      `flux get sources git`. Ensure the URL is correct and the deploy key has
      access.
    - Manifest error. `kubectl describe` may reveal errors from
      `kustomize build` or `kubectl apply`. Fix YAML syntax issues or missing
      dependencies (for example, a `HelmRelease` referencing a `HelmRepository`
      not yet defined).

- Symptom: Wildcard record does not resolve a specific subdomain

  - Verify: `dig TXT <subdomain>.<domain>`
  - Causes/Resolution:
    - Conflicting record. Cloudflare DNS does not apply a wildcard (`*`) to a
      hostname that already has another record (for example, `TXT`, `MX`).
      Remove the conflicting record to allow the wildcard to take effect.[^23]

### 6.3 Comparative Analysis: The GitOps Advantage

The integrated GitOps architecture presented in this guide offers significant
advantages over traditional DNS management paradigms.

- **Manual Management:**
- **Process:** An operator manually logs into the DNS provider’s UI or uses a
  CLI to create, update, or delete records in response to a request.
- **Analysis:** This approach is simple for trivial cases but fails completely
  at scale. It is slow, prone to typos and other human errors, provides no
  auditable history, and requires granting broad permissions to human
  operators, which is a security risk. It creates a significant operational
  bottleneck that impedes development velocity.[^1]
- **Cloud-Provider Specific (IaC-Only):**
- **Process:** DNS records are defined as resources (e.g., `cloudflare_record`)
  in an IaC tool like OpenTofu or Terraform. Changes are managed through a pull
  request workflow against an infrastructure repository.
- **Analysis:** This is a major improvement over manual management, as it makes
  DNS changes declarative, version-controlled, and auditable. However, it
  tightly couples the application deployment lifecycle with the infrastructure
  management lifecycle. An application developer must wait for an
  infrastructure team to review and apply their DNS change, reintroducing a
  bottleneck. This model is also inherently provider-specific and less
  portable.[^1]
- **GitOps with FluxCD & ExternalDNS:**
- **Process:** DNS state is derived directly from Kubernetes application
  manifests stored in a Git repository and is automatically reconciled by
  in-cluster controllers.
- **Analysis:** This model represents the state of the art. It is fully
  automated, self-healing, and highly scalable. The entire history of DNS
  changes is auditable through the Git log. It dramatically increases developer
  velocity by enabling self-service DNS management within established
  guardrails. Because ExternalDNS supports dozens of providers, the core
  application manifests remain portable across different DNS backends. The
  security posture is improved by using narrowly-scoped, machine-to-machine API
  tokens and by removing the need for developers to have direct access to DNS
  provider credentials.[^2] While the initial setup complexity is higher, the
  long-term gains in efficiency, reliability, and security are substantial.

## Part 7: Conclusion and Future Outlook

### 7.1 Summary of Key Benefits

The architecture detailed in this guide, integrating Kubernetes, Cloudflare,
ExternalDNS, FluxCD, and OpenTofu, provides a robust, declarative, and fully
automated solution for managing dynamic DNS in cloud-native environments. The
primary benefits of this GitOps-centric approach can be summarized across four
key pillars:

- **Velocity:** By enabling developers to manage DNS records for their
  applications via familiar Git workflows and Kubernetes manifests, the system
  eliminates traditional operational bottlenecks. This self-service model
  drastically reduces the lead time from code commit to publicly accessible
  endpoint.
- **Reliability:** The declarative nature of GitOps, combined with the
  continuous reconciliation loop provided by FluxCD and ExternalDNS, creates a
  self-healing system. Any manual, out-of-band changes or configuration drift
  are automatically detected and corrected to match the desired state defined
  in Git, leading to a more predictable and stable environment.
- **Security:** The architecture enhances security through multiple layers. It
  relies on narrowly-scoped API tokens with least-privilege permissions,
  removes the need for human operators to have direct access to sensitive
  credentials, and enforces all changes through a version-controlled, auditable
  Git history with mandatory peer review.
- **Consistency:** With Git as the single source of truth, the system ensures
  that the DNS configuration is always consistent with the state of the
  applications running in the Kubernetes cluster. This eliminates configuration
  drift and provides a clear, auditable record of the entire system’s history.

### 7.2 Extending the Architecture: Automated TLS

While this guide provides a complete solution for automated DNS, the logical
next step in securing publicly exposed applications is the automated
provisioning and management of TLS certificates. This can be seamlessly
integrated into the existing architecture using `cert-manager`, another
open-source Kubernetes controller.

`cert-manager` operates on a similar principle to ExternalDNS. It watches
`Ingress` resources, and when it finds one configured for TLS, it automatically
communicates with a certificate authority like Let’s Encrypt to obtain a valid
TLS certificate. It then stores this certificate in a Kubernetes `Secret` and
configures the `Ingress` to use it, enabling HTTPS.[^2]

By deploying `cert-manager` alongside ExternalDNS (also managed via a FluxCD
`HelmRelease`), the entire application exposure pipeline becomes automated: a
single `git push` of an `Ingress` manifest can trigger the creation of a public
DNS record and the issuance of a valid TLS certificate, resulting in a secure,
publicly accessible endpoint within minutes, without any further manual
intervention. This combination represents a truly powerful, end-to-end
declarative solution for modern application delivery on Kubernetes.

## Works cited

[^1]: Automating DNS Management in Kubernetes with External-DNS …,
[https://containerinfra.nl/blog/2024/10/09/automating-dns-management-in-kubernetes-with-external-dns-and-cloudflare/](https://containerinfra.nl/blog/2024/10/09/automating-dns-management-in-kubernetes-with-external-dns-and-cloudflare/)

[^2]: GitOps for Azure Kubernetes Service - Azure Architecture Center |
Microsoft Learn,
[https://learn.microsoft.com/en-us/azure/architecture/example-scenario/gitops-aks/gitops-blueprint-aks](https://learn.microsoft.com/en-us/azure/architecture/example-scenario/gitops-aks/gitops-blueprint-aks)

[^3]: External DNS - Funky Penguin’s Geek Cookbook,
<https://geek-cookbook.funkypenguin.co.nz/kubernetes/external-dns/>

[^4]: external-dns/docs/tutorials/cloudflare.md (GitHub),
[https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/cloudflare.md](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/cloudflare.md)

[^5]: Cloudflare Provider - OpenTofu Registry,
[https://search.opentofu.org/provider/opentofu/cloudflare/latest](https://search.opentofu.org/provider/opentofu/cloudflare/latest)

[^6]: Automate DNS for Your Ingress: Kubernetes + Cloudflare + ExternalDNS | by
Ritik Kesharwani | Jul, 2025 | AWS in Plain English,
[https://aws.plainenglish.io/automate-dns-for-your-ingress-kubernetes-cloudflare-externaldns-133772cc46df](https://aws.plainenglish.io/automate-dns-for-your-ingress-kubernetes-cloudflare-externaldns-133772cc46df)

[^7]: Get Started with Flux - Flux CD,
[https://fluxcd.io/flux/get-started/](https://fluxcd.io/flux/get-started/)

[^8]: Configure external DNS servers dynamically from Kubernetes resources -
GitHub,
[https://github.com/kubernetes-sigs/external-dns](https://github.com/kubernetes-sigs/external-dns)

[^9]: Simplifying DNS Management with ExternalDNS in Kubernetes - Develeap,
[https://www.develeap.com/Simplifying-DNS-Management-with-ExternalDNS-in-Kubernetes/](https://www.develeap.com/Simplifying-DNS-Management-with-ExternalDNS-in-Kubernetes/)

[^10]: What is Flux CD & How Does It Work? [Tutorial] - Spacelift,
[https://spacelift.io/blog/fluxcd](https://spacelift.io/blog/fluxcd)

[^11]: Onboard a domain · Cloudflare Fundamentals docs,
[https://developers.cloudflare.com/fundamentals/manage-domains/add-site/](https://developers.cloudflare.com/fundamentals/manage-domains/add-site/)

[^12]: Flux bootstrap for Gitea - Flux CD,
[https://fluxcd.io/flux/installation/bootstrap/gitea/](https://fluxcd.io/flux/installation/bootstrap/gitea/)

[^13]: Managing Flux | Welcome to Nishanth’s Blog,
[https://blog.nishanthkp.com/docs/devsecops/gitops/flux/managing-flux/](https://blog.nishanthkp.com/docs/devsecops/gitops/flux/managing-flux/)

[^14]: Automatically set home-lab DNS records to Cloudflare using External DNS |
by 楠 - Medium,
[https://medium.com/@fawenyo/automatically-set-home-lab-dns-records-to-cloudflare-using-external-dns-d85eaff326be](https://medium.com/@fawenyo/automatically-set-home-lab-dns-records-to-cloudflare-using-external-dns-d85eaff326be)

[^15]: Exposing Kubernetes Apps to the Internet with Cloudflare Tunnel …,
[https://itnext.io/exposing-kubernetes-apps-to-the-internet-with-cloudflare-tunnel-ingress-controller-and-e30307c0fcb0](https://itnext.io/exposing-kubernetes-apps-to-the-internet-with-cloudflare-tunnel-ingress-controller-and-e30307c0fcb0)

[^16]: cloudflare and ingress-nginx : r/kubernetes - Reddit,
[https://www.reddit.com/r/kubernetes/comments/z2vogg/cloudflare_and_ingressnginx/](https://www.reddit.com/r/kubernetes/comments/z2vogg/cloudflare_and_ingressnginx/)

[^17]: Add cloudflare-proxied annotation to service · Issue #3956 ·
kubernetes-sigs/external-dns,
[https://github.com/kubernetes-sigs/external-dns/issues/3956](https://github.com/kubernetes-sigs/external-dns/issues/3956)

[^18]: Kustomization - Flux CD,
[https://fluxcd.io/flux/components/kustomize/kustomizations/](https://fluxcd.io/flux/components/kustomize/kustomizations/)

[^19]: Manage your Cloudflare domains automatically with an Nginx Ingress
controller and External DNS, together with SSL Certificates through Cert
Manager - Xavier Geerinck,
<https://xaviergeerinck.com/2025/01/28/manage-your-cloudflare-domains-automatically-with-an-nginx-ingress-controller-and-external-dns-together-with-ssl-certificates-through-cert-manager/>

[^20]: Automated DNS Record Management for Kubernetes Resources using
external-dns and AWS Route53 - DEV Community,
[https://dev.to/suin/automated-dns-record-management-for-kubernetes-resources-using-external-dns-and-aws-route53-cnm](https://dev.to/suin/automated-dns-record-management-for-kubernetes-resources-using-external-dns-and-aws-route53-cnm)

[^21]: External-DNS - Automated DNS Management for k3s Homelab - Kamil Błaż,
[https://www.devkblaz.com/blog/external-dns/](https://www.devkblaz.com/blog/external-dns/)

[^22]: Cloudflare CF_API_TOKEN doesn’t work · Issue #4263 · kubernetes …,
[https://github.com/kubernetes-sigs/external-dns/issues/4263](https://github.com/kubernetes-sigs/external-dns/issues/4263)

[^23]: Comparative Analysis of GitOps vs. Traditional Infrastructure Management
Approaches,
[https://www.researchgate.net/publication/388068285_Comparative_Analysis_of_GitOps_vs_Traditional_Infrastructure_Management_Approaches](https://www.researchgate.net/publication/388068285_Comparative_Analysis_of_GitOps_vs_Traditional_Infrastructure_Management_Approaches)
