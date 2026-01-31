"""Dataclasses for nile-valley-infra-k8s input resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RawInputs:
    """Raw CLI and environment inputs before resolution.

    Attributes
    ----------
    cluster_name, environment, region : str | None
        Cluster identifiers from CLI or environment.
    kubernetes_version, node_pools : str | None
        Optional cluster configuration overrides.
    domain, acme_email : str | None
        Domain configuration values.
    gitops_repository, gitops_branch, gitops_token : str | None
        GitOps configuration values.
    vault_address, vault_role_id, vault_secret_id, vault_ca_certificate : str | None
        Vault configuration values.
    digitalocean_token, spaces_access_key, spaces_secret_key : str | None
        Cloud credentials for provisioning and state.
    cloudflare_api_token_secret_name : str | None
        Secret name for the Cloudflare API token.
    enable_traefik, enable_cert_manager, enable_external_dns : str | None
        Feature flags for platform components.
    enable_vault_eso, enable_cnpg : str | None
        Feature flags for Vault ESO and CNPG.
    dry_run : str | None
        Dry-run flag value.
    runner_temp, github_env : Path | None
        Paths for runner temp and GitHub environment file.

    Examples
    --------
    >>> RawInputs(
    ...     cluster_name="preview-1",
    ...     environment="preview",
    ...     region="nyc1",
    ...     kubernetes_version=None,
    ...     node_pools=None,
    ...     domain="example.test",
    ...     acme_email="admin@example.test",
    ...     gitops_repository="leynos/nile-valley-infra",
    ...     gitops_branch="main",
    ...     gitops_token="token",
    ...     vault_address="https://vault.example.test:8200",
    ...     vault_role_id="role",
    ...     vault_secret_id="secret",
    ...     vault_ca_certificate=None,
    ...     digitalocean_token="do-token",
    ...     spaces_access_key="access",
    ...     spaces_secret_key="secret",
    ...     cloudflare_api_token_secret_name="cloudflare-api-token",
    ...     enable_traefik="true",
    ...     enable_cert_manager="true",
    ...     enable_external_dns="true",
    ...     enable_vault_eso="true",
    ...     enable_cnpg="true",
    ...     dry_run="false",
    ...     runner_temp=Path("/tmp"),
    ...     github_env=Path("/tmp/github-env"),
    ... )
    """

    cluster_name: str | None = None
    environment: str | None = None
    region: str | None = None
    kubernetes_version: str | None = None
    node_pools: str | None = None
    domain: str | None = None
    acme_email: str | None = None
    gitops_repository: str | None = None
    gitops_branch: str | None = None
    gitops_token: str | None = None
    vault_address: str | None = None
    vault_role_id: str | None = None
    vault_secret_id: str | None = None
    vault_ca_certificate: str | None = None
    digitalocean_token: str | None = None
    spaces_access_key: str | None = None
    spaces_secret_key: str | None = None
    cloudflare_api_token_secret_name: str | None = None
    enable_traefik: str | None = None
    enable_cert_manager: str | None = None
    enable_external_dns: str | None = None
    enable_vault_eso: str | None = None
    enable_cnpg: str | None = None
    dry_run: str | None = None
    runner_temp: Path | None = None
    github_env: Path | None = None


@dataclass(frozen=True, slots=True)
class ResolvedInputs:
    """Resolved inputs for provisioning and rendering.

    Attributes
    ----------
    cluster_name, environment, region : str
        Core cluster identifiers.
    kubernetes_version : str | None
        Optional Kubernetes version override.
    node_pools : list[dict[str, object]] | None
        Parsed node pool definitions.
    domain, acme_email : str
        Domain configuration values.
    gitops_repository, gitops_branch, gitops_token : str
        GitOps configuration values.
    vault_address, vault_role_id, vault_secret_id : str | None
        Vault configuration values (optional when Vault ESO is disabled).
    vault_ca_certificate : str | None
        Optional Vault CA bundle.
    digitalocean_token, spaces_access_key, spaces_secret_key : str
        Cloud credentials for provisioning and state.
    cloudflare_api_token_secret_name : str
        Secret name for the Cloudflare API token.
    enable_traefik, enable_cert_manager, enable_external_dns : bool
        Feature flags for platform components.
    enable_vault_eso, enable_cnpg : bool
        Feature flags for Vault ESO and CNPG.
    dry_run : bool
        Dry-run flag.
    runner_temp, github_env : Path
        Paths for runner temp and GitHub environment file.

    Examples
    --------
    >>> ResolvedInputs(
    ...     cluster_name="preview-1",
    ...     environment="preview",
    ...     region="nyc1",
    ...     kubernetes_version=None,
    ...     node_pools=None,
    ...     domain="example.test",
    ...     acme_email="admin@example.test",
    ...     gitops_repository="leynos/nile-valley-infra",
    ...     gitops_branch="main",
    ...     gitops_token="token",
    ...     vault_address="https://vault.example.test:8200",
    ...     vault_role_id="role",
    ...     vault_secret_id="secret",
    ...     vault_ca_certificate=None,
    ...     digitalocean_token="do-token",
    ...     spaces_access_key="access",
    ...     spaces_secret_key="secret",
    ...     cloudflare_api_token_secret_name="cloudflare-api-token",
    ...     enable_traefik=True,
    ...     enable_cert_manager=True,
    ...     enable_external_dns=True,
    ...     enable_vault_eso=True,
    ...     enable_cnpg=True,
    ...     dry_run=False,
    ...     runner_temp=Path("/tmp"),
    ...     github_env=Path("/tmp/github-env"),
    ... )
    """

    cluster_name: str
    environment: str
    region: str
    kubernetes_version: str | None
    node_pools: list[dict[str, object]] | None
    domain: str
    acme_email: str
    gitops_repository: str
    gitops_branch: str
    gitops_token: str
    vault_address: str | None
    vault_role_id: str | None
    vault_secret_id: str | None
    vault_ca_certificate: str | None
    digitalocean_token: str
    spaces_access_key: str
    spaces_secret_key: str
    cloudflare_api_token_secret_name: str
    enable_traefik: bool
    enable_cert_manager: bool
    enable_external_dns: bool
    enable_vault_eso: bool
    enable_cnpg: bool
    dry_run: bool
    runner_temp: Path
    github_env: Path
