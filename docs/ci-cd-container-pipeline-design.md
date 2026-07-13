# Architecting a Modern CI/CD Pipeline: From GitHub Actions to Kubernetes on DigitalOcean

______________________________________________________________________

## Part I: The Core Workflow - Building and Publishing to GHCR with GitHub Actions

The foundation of any modern software delivery process is a robust Continuous
Integration (CI) pipeline that reliably transforms source code into a
deployable artifact. In the context of containerized applications, this
artifact is a Docker image. This section details the construction of a
complete, production-ready GitHub Actions workflow to build a container image
and publish it to the GitHub Container Registry (GHCR), progressing from
fundamental authentication principles to advanced, multi-architecture build
strategies.

### Section 1.1: Authenticating to GHCR: The Modern Approach

The GitHub Container Registry (GHCR) offers significant advantages by
co-locating container images with the source code, enabling fine-grained,
repository-level permissions, and integrating seamlessly with the broader
GitHub ecosystem.[^1] Secure and efficient authentication is the first step in
leveraging this registry.

The most secure and recommended method for authenticating to GHCR within a
GitHub Actions workflow is to use the automatically generated
`GITHUB_TOKEN`.[^1] This token is a short-lived installation access token for a
GitHub App that is automatically installed on the repository when Actions are
enabled.[^1] Its permissions are scoped to the repository, and its temporary
nature makes it vastly superior to using long-lived Personal Access Tokens
(PATs), which can pose a significant security risk if compromised.

A critical aspect of using the `GITHUB_TOKEN` is adhering to the principle of
least privilege. This is enforced within the workflow file by explicitly
defining the necessary permissions using the `permissions` key, either at the
top level of the workflow or for a specific job.[^2] For a standard
build-and-push operation, the workflow requires two key permissions:

`packages: write` to allow pushing the image to GHCR, and `contents: read` to
allow the `actions/checkout` step to access the repository's source code.[^1]
Neglecting to configure these permissions can lead to failed jobs and
represents a common oversight in basic pipeline configurations.

The implementation of this authentication process is streamlined by the
official `docker/login-action`. This action handles the necessary Docker login
command, using the `GITHUB_TOKEN` for the password and the `github.actor`
context variable (the user or app that initiated the workflow) for the username.

The following YAML snippet demonstrates a secure login step within a GitHub
Actions job:

```yaml
# .github/workflows/ci.yml

name: CI Pipeline

on:
  push:
    branches: [ main ]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Log in to the GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      #... subsequent build and push steps

```

This configuration establishes a secure, temporary authentication context,
allowing the subsequent steps in the job to interact with GHCR without handling
long-lived credentials directly.

### Section 1.2: Crafting the Build and Push Workflow

With authentication established, the next step is to build the Docker image and
push it to the registry. While the GitHub Marketplace contains various
community-provided actions for this purpose, the ecosystem has matured around a
suite of official, composable actions provided by Docker.[^3] The cornerstone
of this suite is the

`docker/build-push-action`, which offers the versatility and features required
for production-grade workflows.[^4] This action leverages Docker Buildx under
the hood, providing full support for advanced features like multi-platform
builds, caching, and secrets management.[^4]

The `docker/build-push-action` is configured through a set of inputs. The most
essential are:

- `context`: The build context, typically `.` for the repository root.
- `file`: The path to the Dockerfile, e.g., `./Dockerfile`.
- `push`: A boolean (`true` or `false`) that determines whether the built image
  should be pushed to the registry.
- `tags`: A comma-separated list of tags to apply to the image.

While tags can be hardcoded, a robust CI pipeline should generate them
dynamically based on the context of the Git event that triggered the workflow.
This is where the `docker/metadata-action` becomes invaluable.[^1] This utility
action can inspect the Git context (e.g., a push to a branch, a new tag, a pull
request) and generate a set of logical and informative image tags. This
elevates the workflow from a simple script to an intelligent automation tool
that produces versioned artifacts, such as tagging an image with the branch
name, the short commit SHA, and applying the

`latest` tag only for pushes to the default branch.

The following YAML example demonstrates a complete single-architecture build
job, integrating code checkout, login, metadata extraction, and the final
build-and-push step:

```yaml
# .github/workflows/ci.yml

name: CI Pipeline

on:
  push:
    branches: [ main ]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Log in to the GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

```

This compositional approach, where specialized actions for login, metadata, and
building are combined, represents a mature pattern in CI/CD. Early iterations
of CI tooling often relied on monolithic, all-in-one actions that proved
inflexible as use cases grew more complex. The modern approach, akin to the
Unix philosophy of "do one thing and do it well," provides greater power and
maintainability by allowing engineers to assemble a pipeline from discrete,
specialized components.[^4]

### Section 1.3: Advanced Strategy: Multi-Architecture Builds

The modern computing landscape is increasingly heterogeneous. Applications must
run on traditional `amd64` (x86-64) servers, ARM-based cloud instances like AWS
Graviton, and developers' local machines, which often include ARM-based Apple
Silicon.[^5] Building multi-architecture container images is therefore no
longer a niche requirement but a mainstream necessity.

GitHub Actions can produce multi-architecture images from a single `amd64`
runner through emulation. This requires two additional setup actions from the
Docker suite:

1. `docker/setup-qemu-action`: This action configures QEMU, a generic machine
   emulator, which allows the runner to execute instructions for different CPU
   architectures.[^4]
2. `docker/setup-buildx-action`: This action initializes Docker Buildx, an
   extension that enables advanced build capabilities, including multi-platform
   builds.[^4]

With these actions in place, the `docker/build-push-action` can be instructed
to build for multiple platforms by passing a comma-separated list to its
`platforms` input, for example, `linux/amd64,linux/arm64`.

However, this convenience comes at a significant cost. Emulating a
CPU-intensive task like code compilation is substantially slower than native
execution.[^6] While functionally correct, a QEMU-based multi-architecture
build can take dramatically longer than a native build. This performance
bottleneck is a primary driver for the emergence of specialized build
acceleration services, which will be analysed in Part III of this report.

The following workflow demonstrates a complete, multi-architecture build
pipeline, incorporating all the necessary setup steps:

```yaml
# .github/workflows/ci.yml

name: CI Pipeline

on:
  push:
    branches: [ main ]

jobs:
  build-and-push-multi-arch:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to the GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

```

This workflow represents the current best practice for building
multi-architecture images using standard GitHub-hosted runners, providing a
solid foundation for the deployment phase.

______________________________________________________________________

## Part II: Deployment - Integrating with DigitalOcean Kubernetes Service (DOKS)

With a container image successfully built and published to GHCR, the CI
pipeline must transition to Continuous Deployment (CD). This part details the
process of automating the deployment of the containerized application to a
DigitalOcean Kubernetes Service (DOKS) cluster, bridging the gap between the CI
system and the production environment.

### Section 2.1: Establishing Trust: Kubernetes Image Pull Secrets for Private GHCR

A DOKS cluster is an external system with no inherent access to a private
GitHub Container Registry. To pull the private image, the Kubernetes cluster
must be provided with credentials. This is achieved by creating an
`imagePullSecret`.[^7] This process establishes a secure trust relationship
between the two distinct platforms.

The core of this process is a GitHub Personal Access Token (PAT). Following the
principle of least privilege, this PAT should be created with the absolute
minimum scope required: `read:packages`.[^8] This ensures that even if the
token were compromised, its access is limited to reading container images and
nothing else.

Once the PAT is generated, it is used to create a Kubernetes secret of type
`docker-registry`. The `kubectl` command-line tool provides a direct way to
create this secret within the target cluster and namespace. The command
requires the registry server (`ghcr.io`), a username (the GitHub username), and
the PAT as the password.[^7]

The command to create the secret is as follows:

```bash
kubectl create secret docker-registry ghcr-pull-secret \
  --namespace=<your-namespace> \
  --docker-server=ghcr.io \
  --docker-username=<your-github-username> \
  --docker-password=<your-pat-with-read:packages-scope>

```

After the secret is created, it must be associated with the pods that need to
pull the image. This can be done in two ways:

1. **Per-Deployment Specification:** The most explicit method is to add an
   `imagePullSecrets` section to the pod template within the Deployment
   manifest, referencing the newly created secret by name.[^9] This provides
   clear, declarative configuration on a per-workload basis.
2. **Service Account Patching:** For convenience, the default service account
   in the namespace can be patched to include the `imagePullSecret`.[^9] Any
   new pod created in that namespace without a specified service account will
   automatically inherit this secret. While this simplifies deployment
   manifests, it grants pull access more broadly, which may have security
   implications depending on the environment.

### Section 2.2: Automating Deployment from GitHub Actions

The deployment process itself can be fully automated within the GitHub Actions
workflow. This requires the workflow runner to authenticate with the
DigitalOcean API and then interact with the Kubernetes cluster using `kubectl`.

The connection to DigitalOcean is established using the official
`digitalocean/action-doctl@v2` action.[^10] This action requires a

`DIGITALOCEAN_ACCESS_TOKEN`, which should be stored as an encrypted secret in
the GitHub repository settings. Once authenticated, the workflow can use
`doctl`, the DigitalOcean command-line tool.

The next step is to securely fetch the Kubernetes cluster's configuration file
(`kubeconfig`). The `doctl kubernetes cluster kubeconfig save` command
accomplishes this. For enhanced security, it is critical to use the
`--expiry-seconds` flag to generate short-lived credentials for the cluster,
minimizing the window of exposure.[^10]

Ensuring the Kubernetes deployment uses the newly built image tag is crucial
for automated release. The command
`kubectl set image deployment/${K8S_DEPLOYMENT_NAME} app=${TAGGED_IMAGE}`[^10]
patches the live Deployment imperatively. It is a non-GitOps workaround best
suited to ad-hoc fixes or development clusters.

In a GitOps workflow managed by Flux, avoid direct cluster edits. Commit the
new image tag to the `HelmRelease` in the Git repository and let Flux reconcile
the change into the cluster. For more complex applications, tools like
Kustomize or Helm provide structured manifest management.

With the image updated and the `kubeconfig` in place, the deployment rolls out
immediately. This entire sequence demonstrates that a CI/CD pipeline is
fundamentally a chain of authenticated operations across distributed systems.
The workflow runner acts as a trusted orchestrator, using one set of
credentials (the DO token) to gain access to a second system (the Kubernetes
cluster), which in turn uses a provisioned credential (the `imagePullSecret`)
to access a third system (GHCR). Securely managing these credential boundaries
is the most critical aspect of pipeline security.

### Section 2.3: Verifying and Finalizing the Deployment

A professional deployment pipeline does not simply "fire and forget." It must
verify that the deployment was successful. The `kubectl rollout status` command
is an essential tool for this purpose.[^10] By adding this command as a final
step in the job, the workflow will pause and wait for the Kubernetes deployment
to complete its rollout. If the new pods fail to start or the deployment times
out, the

`rollout status` command will exit with an error code, causing the entire
workflow job to fail. This provides immediate, unambiguous feedback directly
within the CI/CD system, preventing silent failures.

Combining all the elements from Parts I and II results in a complete,
end-to-end CI/CD pipeline. The following YAML file represents a
production-ready workflow that builds a multi-architecture image, pushes it to
GHCR, and deploys it to a DOKS cluster, including verification.

```yaml
# .github/workflows/build-and-deploy.yml

name: Build and Deploy to DOKS

on:
  push:
    branches: [ main ]

env:
  # Define variables for reuse
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  DO_CLUSTER_NAME: <your-doks-cluster-name>
  K8S_DEPLOYMENT_NAME: <your-deployment-name>
  K8S_NAMESPACE: app

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag: ${{ fromJSON(steps.meta.outputs.json).tags[0].split(':')[1] }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=,format=short

      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    runs-on: ubuntu-latest
    needs: build-and-push
    environment: production
    concurrency:
      group: doks-deploy-${{ github.ref }}
      cancel-in-progress: true
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install doctl
        uses: digitalocean/action-doctl@v2
        with:
          token: ${{ secrets.DIGITALOCEAN_ACCESS_TOKEN }}

      - name: Save Kubeconfig
        run: doctl kubernetes cluster kubeconfig save --expiry-seconds 600 ${{ env.DO_CLUSTER_NAME }}

      - name: Ensure namespace exists
        run: kubectl get ns ${{ env.K8S_NAMESPACE }} || kubectl create ns ${{ env.K8S_NAMESPACE }}

      - name: Deploy to DOKS
        run: |
          TAGGED_IMAGE="${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ needs.build-and-push.outputs.image_tag }}"
          kubectl set image deployment/${{ env.K8S_DEPLOYMENT_NAME }} \
            app=${TAGGED_IMAGE} \
            --namespace ${{ env.K8S_NAMESPACE }}

      - name: Verify deployment
        run: kubectl rollout status deployment/${{ env.K8S_DEPLOYMENT_NAME }} --namespace ${{ env.K8S_NAMESPACE }} --timeout=5m

```

Note: replace `app` with the container name defined in your Deployment spec.

______________________________________________________________________

## Part III: Accelerating Container Builds - A Comparative Analysis

While the workflow established in the previous parts is functionally complete,
its performance, particularly for multi-architecture builds, is limited by the
standard infrastructure provided by GitHub. This section addresses the
performance bottleneck by providing a detailed, data-driven comparison of
alternative solutions designed to accelerate container builds.

### Section 3.1: The Baseline - Standard GitHub-Hosted Runners

Standard GitHub-hosted runners provide a convenient and tightly integrated
execution environment. The default `ubuntu-latest` runner is typically a 2-vCPU
virtual machine, which is adequate for many CI tasks but can become a
bottleneck for CPU-intensive operations like compiling code within a Docker
build.[^6]

Two primary performance challenges arise with standard runners in the context
of Docker builds:

1. **Inefficient Caching:** The standard `actions/cache` mechanism is designed
   for files and directories, not Docker layers. To cache Docker layers, it
   must create a large tarball of the cache directory, upload it, and then
   download and extract it on subsequent runs. This I/O-heavy process can often
   take more time than is saved by the cache itself, especially for projects
   with large or numerous layers.[^5]
2. **The Emulation Tax:** As established in Section 1.3, performing
   multi-architecture builds via QEMU imposes a severe performance penalty.
   Emulating an ARM CPU on an x86 machine to compile code is orders of
   magnitude slower than native compilation, turning what might be a few
   minutes of build time into 30 minutes or more.[^6]

These limitations create a clear need for solutions that offer either more
powerful hardware, more intelligent caching, or native build environments.

### Section 3.2: Blacksmith: Raw Compute Power as a Service

Blacksmith's core value proposition is providing significantly faster hardware
for GitHub Actions jobs. It offers runners that run on "bare‑metal gaming CPUs"
with high single‑core performance, directly addressing the compute limitations
of standard runners.[^11]

The integration model for Blacksmith is that of a "drop-in" runner replacement.
A user migrates by simply changing the `runs-on` key in their workflow YAML
from `ubuntu-latest` to a Blacksmith-provided label.[^11] This approach is
horizontal; it accelerates every step within the job—checkout, setup, testing,
and building—by providing a more powerful underlying machine.

Blacksmith's pricing is per-minute, but at a rate lower than GitHub's standard
runners. The business model relies on completing jobs much faster, leading to
an overall cost reduction of up to 75%.[^11] It also offers features like
observability dashboards to help diagnose slow jobs.[^11] It is important to
note that while Blacksmith provides faster hardware and dependency caching,
advanced Docker layer caching is an optional, paid add-on.[^12]

### Section 3.3: Depot: A Specialized, Distributed Build Service

Depot takes a different approach. Instead of replacing the entire runner, it
focuses exclusively on accelerating the `docker build` command itself. It is a
specialized, remote container build service.[^5]

Depot's integration model is an "action replacement." A user migrates by
changing the `uses` key from `docker/build-push-action` to
`depot/build-push-action@v1`.[^13] This is a vertical intervention, targeting a
specific, known bottleneck. When this action is invoked, the build is not
executed on the GitHub runner. Instead, it is offloaded to Depot's powerful
remote builders (e.g., 16 CPUs, 32 GB RAM).[^5]

This architectural difference enables two key features that directly solve the
baseline problems:

1. **Persistent SSD Caching:** Each Depot project is backed by a large,
   persistent NVMe SSD cache. This cache is instantly available to every build
   without any slow download/upload steps, dramatically speeding up incremental
   builds.[^5]
2. **Native Multi-Platform Builds:** Depot maintains a fleet of both `amd64`
   and `arm64` builders. When a multi-platform build is requested, Depot
   intelligently routes the build for each architecture to a native machine,
   completely eliminating the QEMU emulation tax.[^13]

Depot offers tiered pricing plans based on build minutes and cache storage,
with support for modern authentication methods like OIDC to avoid static
tokens.[^14]

### Section 3.4: Synthesis and Decision Framework

The choice between these solutions depends on the specific nature of the
performance bottleneck in a given workflow. Blacksmith's runner replacement is
a general-purpose optimization, while Depot's action replacement is a
specialized, surgical solution for slow Docker builds. Profiling a workflow to
understand whether the time is spent inside or outside the `docker build` step
is essential to making the correct architectural choice.

The following table provides a direct comparison to aid in this decision-making
process.

| Feature                | Standard GitHub Runner                             | Blacksmith                                                      | Depot                                                                                      |
| ---------------------- | -------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Integration Method** | Default (`runs-on: ubuntu-latest`)                 | Runner Replacement (`runs-on: blacksmith-runner`)               | Action Replacement (`uses: depot/build-push-action`)                                       |
| **Primary Benefit**    | Convenience, no extra cost                         | Faster general-purpose compute (all job steps)                  | Specialized `docker build` acceleration                                                    |
| **Caching Mechanism**  | Slow I/O with `actions/cache` (tarball-based)      | Faster dependency caching; Docker layer cache is an add-on      | Instant, persistent SSD cache for Docker layers                                            |
| **Multi-Arch Support** | Slow (QEMU Emulation)                              | Faster hardware, but still relies on slow QEMU emulation        | Fast (Native Compilation on dedicated ARM/x86 builders)                                    |
| **Pricing Model**      | Included minutes, then per-minute                  | Per-minute (lower rate, faster execution)                       | Tiered plans (build minutes + storage)                                                     |
| **Ideal Use Case**     | Simple, infrequent builds; cost-sensitive projects | Workflows where the entire job is slow (e.g., long test suites) | Workflows where `docker build` is the primary bottleneck, especially with multi-arch needs |

**Decision Guidance:**

- **Select Standard Runners when:** Budgets are extremely constrained, builds
  are simple and fast enough, and multi-architecture support is not a priority.
- **Select Blacksmith when:** The entire CI job is a bottleneck, not just the
  container build. If extensive test suites, code analysis, or other non-Docker
  steps are consuming the most time, Blacksmith's faster general-purpose
  hardware will provide the most significant benefit with minimal change to the
  workflow file.
- **Select Depot when:** The `docker build` step is definitively the slowest
  part of the pipeline. This is especially true for projects with large
  dependencies, complex Dockerfiles, and a frequent need for fast, reliable
  multi-architecture images. Depot's native builds and intelligent caching
  provide a targeted solution that a faster runner alone cannot match.

______________________________________________________________________

## Part IV: Architecting for Portability - A Vendor-Agnostic CI/CD Pipeline

While a finely tuned pipeline on a specific platform is valuable, strategic
long-term architecture requires considering portability. A vendor-agnostic
pipeline is not only resilient to platform changes but also enables powerful
optimization strategies. This final section outlines the principles and
practices for building a flexible and future-proof CI/CD workflow.

### Section 4.1: Principles of Agnostic Pipeline Design

The fundamental principle of an agnostic pipeline is abstraction: separating
the _what_ (the essential logic of the pipeline) from the _how_ (the specific
syntax of the CI provider).[^15]

- **Best Practice 1: Script Your Logic:** The most effective technique is to
  encapsulate the core logic of building, testing, and deploying into
  standalone shell scripts (e.g., `./scripts/build.sh`, `./scripts/deploy.sh`).
  The GitHub Actions YAML file then becomes a thin orchestration layer that
  simply calls these scripts. This makes the core logic instantly portable to
  any CI system capable of executing a shell script, from GitLab CI to a local
  developer machine.[^15]
- **Best Practice 2: Minimize Platform-Specific Actions:** A pipeline that
  heavily relies on a rich ecosystem of third-party, platform-specific actions
  becomes difficult to migrate. Each action represents a dependency that must
  be replaced. A vendor-agnostic approach favours using native command-line
  tools (`docker`, `kubectl`, `sed`) within scripts over platform-specific
  abstractions, unless an action provides irreplaceable value (e.g.,
  `actions/checkout` for efficiently fetching source code).[^15]
- **Best Practice 3: Use Environment Variables for Configuration:** Hardcoding
  values like registry names, cluster identifiers, or image names directly into
  scripts or YAML files creates tight coupling. Abstracting these
  configurations into environment variables allows the same scripts to be
  reused across different environments (dev, staging, prod) and even different
  cloud providers by simply changing the variables passed into the CI job.[^16]

For teams with the most stringent portability requirements, advanced tools like
Dagger are emerging. Dagger allows pipelines to be defined as code in a
general-purpose programming language (like Go or Python) and executed within
containers. This offers the ultimate level of abstraction, making the pipeline
definition itself completely portable across any CI provider that can run the
Dagger engine.[^17]

### Section 4.2: Implementing a Switchable Build Provider Strategy

A practical application of agnostic design is creating a single workflow that
can dynamically select its build provider. This allows a team to test a new
provider like Depot alongside their existing setup or to optimize for cost and
speed based on the context of the run.

This is implemented using conditional logic in GitHub Actions. The `if` keyword
can be placed on any step to control its execution based on an expression.[^18]
It is important to note that GitHub Actions does not have an

`else` or `elseif` construct; conditional branches must be implemented as
separate steps with mutually exclusive or inverted `if` conditions.[^19]

To allow users to choose the provider, the `workflow_dispatch` trigger can be
configured with `inputs`. This exposes a UI on the GitHub Actions page where a
user can manually run the workflow and select an option from a dropdown menu,
which then becomes available in the `github.event.inputs` context.

The following YAML example demonstrates a workflow that allows a user to choose
between the `default` Docker builder and the `depot` builder:

```yaml
# .github/workflows/manual-build.yml

name: Manual Build with Provider Choice

on:
  workflow_dispatch:
    inputs:
      builder:
        description: 'Build provider to use'
        required: true
        default: 'default'
        type: choice
        options:
        - default
        - depot

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write # Required for Depot OIDC

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}

      - name: Build and push (Default)
        if: github.event.inputs.builder == 'default'
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push (Depot)
        if: github.event.inputs.builder == 'depot'
        uses: depot/build-push-action@v1
        with:
          project: <your-depot-project-id> # From Depot project settings
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

```

### Section 4.3: Beyond Build Runners: A Holistic Agnostic Strategy

The principles of abstraction and conditional logic can be applied to the
entire pipeline. The deployment scripts can be parameterized to accept a
registry URL and Kubernetes context as arguments, allowing the same workflow to
target GHCR/DOKS with one set of variables and, for example, Amazon ECR/EKS
with another.

Furthermore, GitHub Actions' `strategy: matrix` feature can be used for
advanced multi-provider validation.[^20] A matrix could define jobs that run
the same test suite on a standard runner, a larger GitHub runner, and a
Blacksmith runner simultaneously. This allows for continuous performance
comparison and ensures that the application remains compatible across different
execution environments.

This leads to a powerful realization: a well-architected, vendor-agnostic
pipeline is not merely a tool for disaster recovery or migration. It is a
strategic asset for active optimization. By combining conditional logic with an
understanding of different provider capabilities, a workflow can make
intelligent, dynamic decisions about resource allocation. For example, a
workflow could be configured to:

- Use the free, slower standard runner for routine builds on pull requests
  (`if: github.event_name == 'pull_request'`).
- Use the premium, faster Depot builder for critical-path deployments to the
  main branch (`if: github.ref == 'refs/heads/main'`).

This approach allows an organization to dynamically manage the trade-off
between speed and cost on a per-run basis, representing a highly mature and
efficient approach to CI/CD resource management.

The appropriate level of abstraction depends on the project's context. The
following matrix provides guidance on selecting a strategy.

| Project Complexity                         | Recommended Agnostic Strategy                   | Rationale                                                                                            |
| ------------------------------------------ | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Solo Project, Single Cloud**             | Minimal Abstraction (Platform-Specific Actions) | Speed of development is paramount; the cost of abstraction outweighs the low risk of vendor lock-in. |
| **Team Project, Multi-Environment**        | Script-Based Abstraction                        | Encapsulating logic in scripts ensures consistency between dev/staging/prod and is easily portable.  |
| **Enterprise, Strict Portability Mandate** | Advanced Abstraction (Dagger Engine or similar) | Guarantees true portability and satisfies strict governance requirements for CI/CD infrastructure.   |

By adopting these principles, teams can build CI/CD pipelines that are not only
powerful and efficient today but also flexible and resilient enough to adapt to
the technological and business needs of tomorrow.

[^1]: Publishing and installing a package with GitHub Actions - GitHub Docs,
[https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions)
[^2]: Use GITHUB_TOKEN for authentication in workflows - GitHub Docs,
[https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token)
[^3]: Build Docker Image and Push to GHCR, Docker Hub, or AWS ECR — GitHub
Marketplace,
[https://github.com/marketplace/actions/build-docker-image-and-push-to-ghcr-docker-hub-or-aws-ecr](https://github.com/marketplace/actions/build-docker-image-and-push-to-ghcr-docker-hub-or-aws-ecr) [https://github.com/marketplace/actions/push-to-ghcr](https://github.com/marketplace/actions/push-to-ghcr)
[^4]: GitHub Action to build and push Docker images with Buildx,
[https://github.com/docker/build-push-action](https://github.com/docker/build-push-action)
[^5]: Depot - GitHub, [https://github.com/depot](https://github.com/depot)
[^6]: GitHub Actions container builds take forever : r/rust - Reddit,
[https://www.reddit.com/r/rust/comments/1n4s4xb/github_actions_container_builds_take_forever/](https://www.reddit.com/r/rust/comments/1n4s4xb/github_actions_container_builds_take_forever/) [https://docs.docker.com/build/ci/github-actions/multi-platform/](https://docs.docker.com/build/ci/github-actions/multi-platform/)
[^7]: Pull an Image from a Private Registry | Kubernetes,
[https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)
[^8]: What is the appropriate way to set image pull secrets for images being
sourced from GitHub to avoid pull rate limits? Community Discussion #160722,
[https://github.com/orgs/community/discussions/160722](https://github.com/orgs/community/discussions/160722) [https://www.deploykf.org/guides/platform/image-pull-secrets/](https://www.deploykf.org/guides/platform/image-pull-secrets/) [https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_secret_docker-registry/](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_secret_docker-registry/)
[^9]: How to Use Your Private DigitalOcean Container Registry with Docker and
Kubernetes,
[https://docs.digitalocean.com/products/container-registry/how-to/use-registry-docker-kubernetes/](https://docs.digitalocean.com/products/container-registry/how-to/use-registry-docker-kubernetes/)
[^10]: Enable Push-to-Deploy on DigitalOcean Kubernetes Using GitHub Actions,
[https://docs.digitalocean.com/products/container-registry/how-to/enable-push-to-deploy/](https://docs.digitalocean.com/products/container-registry/how-to/enable-push-to-deploy/)
[^11]: Blacksmith: The Fastest Way to Run GitHub Actions,
[https://www.blacksmith.sh/](https://www.blacksmith.sh/) [https://www.blacksmith.sh/github-actions-cost-reduction](https://www.blacksmith.sh/github-actions-cost-reduction)
[^12]: Blacksmith Pricing | Fast GitHub Actions with Up to 75% Cost Savings,
[https://www.blacksmith.sh/pricing](https://www.blacksmith.sh/pricing) [https://github.com/depot/build-push-action](https://github.com/depot/build-push-action)
[^13]: GitHub Actions | Integrations | Depot - [Depot.dev](https://depot.dev),
[https://depot.dev/integrations/github-actions](https://depot.dev/integrations/github-actions)
[^14]: GitHub Actions | Container Builds | Depot Documentation,
[https://depot.dev/docs/container-builds/reference/github-actions](https://depot.dev/docs/container-builds/reference/github-actions) [https://depot.dev/docs/container-builds/overview](https://depot.dev/docs/container-builds/overview) [https://depot.dev/pricing](https://depot.dev/pricing)
[^15]: Designing healthy and agnostic CI/CD pipelines | avivace,
[https://avivace.com/posts/agnostic-cicd/](https://avivace.com/posts/agnostic-cicd/) [https://stackoverflow.com/questions/59241249/how-can-i-run-github-actions-workflows-locally](https://stackoverflow.com/questions/59241249/how-can-i-run-github-actions-workflows-locally)
[^16]: CICD Patterns with GitHub Actions and Docker - Hosting Data Apps -
Analythium Solutions,
[https://hosting.analythium.io/cicd-patterns-with-github-actions-and-docker/](https://hosting.analythium.io/cicd-patterns-with-github-actions-and-docker/)
[^17]: Becoming CI Provider Agnostic With Dagger | Arsh Sharma,
[https://arshsharma.com/posts/2025-02-10-ci-agnostic-dagger/](https://arshsharma.com/posts/2025-02-10-ci-agnostic-dagger/)
[^18]: Evaluate expressions in workflows and actions - GitHub Docs,
[https://docs.github.com/actions/reference/evaluate-expressions-in-workflows-and-actions](https://docs.github.com/actions/reference/evaluate-expressions-in-workflows-and-actions) [https://resources.github.com/learn/pathways/automation/advanced/advanced-workflow-configurations-in-github-actions/](https://resources.github.com/learn/pathways/automation/advanced/advanced-workflow-configurations-in-github-actions/)
[^19]: GitHub Actions: Does the IF have an ELSE? - Stack Overflow,
[https://stackoverflow.com/questions/60916931/github-actions-does-the-if-have-an-else](https://stackoverflow.com/questions/60916931/github-actions-does-the-if-have-an-else) [https://hungvu.tech/advanced-github-actions-conditional-workflow/](https://hungvu.tech/advanced-github-actions-conditional-workflow/)
[^20]: Using jobs in a workflow - GitHub Docs,
[https://docs.github.com/actions/using-jobs/using-jobs-in-a-workflow](https://docs.github.com/actions/using-jobs/using-jobs-in-a-workflow) [https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow)
