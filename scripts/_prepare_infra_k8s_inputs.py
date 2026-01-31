"""Resolve and prepare inputs for the nile-valley-infra-k8s action.

This module centralizes input resolution, validation, and GITHUB_ENV exports
for the nile-valley-infra-k8s GitHub Action.

Examples
--------
Resolve inputs and export them for downstream steps:

>>> raw = RawInputs(
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
>>> inputs = _resolve_all_inputs(raw)
>>> prepare_inputs(inputs)
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from scripts._input_resolution import InputResolution, resolve_input
from scripts._infra_k8s import (
    append_github_env,
    mask_secret,
    parse_bool,
    parse_node_pools,
    validate_cluster_name,
)
from scripts._prepare_infra_k8s_models import RawInputs, ResolvedInputs

type Mask = Callable[[str], None]


def _resolve_cluster_config(
    raw: RawInputs,
) -> tuple[str, str, str, str | None, str | None]:
    """Resolve cluster configuration inputs."""
    cluster_name = resolve_input(
        raw.cluster_name,
        InputResolution(env_key="INPUT_CLUSTER_NAME", required=True),
    )
    environment = resolve_input(
        raw.environment,
        InputResolution(env_key="INPUT_ENVIRONMENT", required=True),
    )
    region = resolve_input(
        raw.region,
        InputResolution(env_key="INPUT_REGION", required=True),
    )
    kubernetes_version = resolve_input(
        raw.kubernetes_version,
        InputResolution(env_key="INPUT_KUBERNETES_VERSION"),
    )
    node_pools_raw = resolve_input(
        raw.node_pools,
        InputResolution(env_key="INPUT_NODE_POOLS"),
    )
    return (
        cluster_name,
        environment,
        region,
        kubernetes_version,
        node_pools_raw,
    )


def _resolve_domain_config(raw: RawInputs) -> tuple[str, str]:
    """Resolve domain configuration inputs."""
    domain = resolve_input(
        raw.domain,
        InputResolution(env_key="INPUT_DOMAIN", required=True),
    )
    acme_email = resolve_input(
        raw.acme_email,
        InputResolution(env_key="INPUT_ACME_EMAIL", required=True),
    )
    return domain, acme_email


def _resolve_gitops_config(raw: RawInputs) -> tuple[str, str, str]:
    """Resolve GitOps configuration inputs."""
    gitops_repository = resolve_input(
        raw.gitops_repository,
        InputResolution(env_key="INPUT_GITOPS_REPOSITORY", required=True),
    )
    gitops_branch = resolve_input(
        raw.gitops_branch,
        InputResolution(env_key="INPUT_GITOPS_BRANCH", default="main"),
    )
    gitops_token = resolve_input(
        raw.gitops_token,
        InputResolution(env_key="INPUT_GITOPS_TOKEN", required=True),
    )
    return gitops_repository, gitops_branch, gitops_token


def _resolve_vault_config(
    raw: RawInputs,
    *,
    vault_required: bool,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Resolve vault configuration inputs."""
    vault_address = resolve_input(
        raw.vault_address,
        InputResolution(env_key="INPUT_VAULT_ADDRESS", required=vault_required),
    )
    vault_role_id = resolve_input(
        raw.vault_role_id,
        InputResolution(env_key="INPUT_VAULT_ROLE_ID", required=vault_required),
    )
    vault_secret_id = resolve_input(
        raw.vault_secret_id,
        InputResolution(env_key="INPUT_VAULT_SECRET_ID", required=vault_required),
    )
    vault_ca_certificate = resolve_input(
        raw.vault_ca_certificate,
        InputResolution(env_key="INPUT_VAULT_CA_CERTIFICATE"),
    )
    return vault_address, vault_role_id, vault_secret_id, vault_ca_certificate


def _resolve_cloud_credentials(
    raw: RawInputs,
) -> tuple[str | None, str | None, str | None]:
    """Resolve cloud credential inputs."""
    digitalocean_token = resolve_input(
        raw.digitalocean_token,
        InputResolution(env_key="INPUT_DIGITALOCEAN_TOKEN", required=True),
    )
    spaces_access_key = resolve_input(
        raw.spaces_access_key,
        InputResolution(env_key="INPUT_SPACES_ACCESS_KEY", required=True),
    )
    spaces_secret_key = resolve_input(
        raw.spaces_secret_key,
        InputResolution(env_key="INPUT_SPACES_SECRET_KEY", required=True),
    )
    return digitalocean_token, spaces_access_key, spaces_secret_key


def _resolve_feature_flags(
    raw: RawInputs,
) -> tuple[str, str, str, str, str, str]:
    """Resolve feature flag inputs."""
    cloudflare_api_token_secret_name = resolve_input(
        raw.cloudflare_api_token_secret_name,
        InputResolution(
            env_key="INPUT_CLOUDFLARE_API_TOKEN_SECRET_NAME",
            default="cloudflare-api-token",
        ),
    )
    enable_traefik = resolve_input(
        raw.enable_traefik,
        InputResolution(env_key="INPUT_ENABLE_TRAEFIK", default="true"),
    )
    enable_cert_manager = resolve_input(
        raw.enable_cert_manager,
        InputResolution(env_key="INPUT_ENABLE_CERT_MANAGER", default="true"),
    )
    enable_external_dns = resolve_input(
        raw.enable_external_dns,
        InputResolution(env_key="INPUT_ENABLE_EXTERNAL_DNS", default="true"),
    )
    enable_vault_eso = resolve_input(
        raw.enable_vault_eso,
        InputResolution(env_key="INPUT_ENABLE_VAULT_ESO", default="true"),
    )
    enable_cnpg = resolve_input(
        raw.enable_cnpg,
        InputResolution(env_key="INPUT_ENABLE_CNPG", default="true"),
    )
    return (
        cloudflare_api_token_secret_name,
        enable_traefik,
        enable_cert_manager,
        enable_external_dns,
        enable_vault_eso,
        enable_cnpg,
    )


def _resolve_execution_config(raw: RawInputs) -> tuple[str, Path, Path]:
    """Resolve execution configuration inputs."""
    dry_run = resolve_input(
        raw.dry_run,
        InputResolution(env_key="INPUT_DRY_RUN", default="false"),
    )
    runner_temp = resolve_input(
        raw.runner_temp,
        InputResolution(
            env_key="RUNNER_TEMP",
            default=Path(tempfile.gettempdir()),
            as_path=True,
        ),
    )
    github_env = resolve_input(
        raw.github_env,
        InputResolution(
            env_key="GITHUB_ENV",
            default=Path(tempfile.gettempdir()) / "github-env-undefined",
            as_path=True,
        ),
    )
    return dry_run, runner_temp, github_env


def _resolve_all_inputs(raw: RawInputs) -> ResolvedInputs:
    """Resolve CLI and environment inputs to their canonical types."""
    (
        cluster_name,
        environment,
        region,
        kubernetes_version,
        node_pools_raw,
    ) = _resolve_cluster_config(raw)
    domain, acme_email = _resolve_domain_config(raw)
    gitops_repository, gitops_branch, gitops_token = _resolve_gitops_config(raw)
    (
        digitalocean_token,
        spaces_access_key,
        spaces_secret_key,
    ) = _resolve_cloud_credentials(raw)
    (
        cloudflare_api_token_secret_name,
        enable_traefik,
        enable_cert_manager,
        enable_external_dns,
        enable_vault_eso,
        enable_cnpg,
    ) = _resolve_feature_flags(raw)
    dry_run, runner_temp, github_env = _resolve_execution_config(raw)

    vault_eso_enabled = parse_bool(str(enable_vault_eso) if enable_vault_eso else None)
    (
        vault_address,
        vault_role_id,
        vault_secret_id,
        vault_ca_certificate,
    ) = _resolve_vault_config(raw, vault_required=vault_eso_enabled)

    # Validate cluster name format
    validated_cluster_name = validate_cluster_name(str(cluster_name))

    return ResolvedInputs(
        cluster_name=validated_cluster_name,
        environment=str(environment),
        region=str(region),
        kubernetes_version=str(kubernetes_version) if kubernetes_version else None,
        node_pools=parse_node_pools(str(node_pools_raw) if node_pools_raw else None),
        domain=str(domain),
        acme_email=str(acme_email),
        gitops_repository=str(gitops_repository),
        gitops_branch=str(gitops_branch),
        gitops_token=str(gitops_token),
        vault_address=str(vault_address) if vault_address else None,
        vault_role_id=str(vault_role_id) if vault_role_id else None,
        vault_secret_id=str(vault_secret_id) if vault_secret_id else None,
        vault_ca_certificate=str(vault_ca_certificate) if vault_ca_certificate else None,
        digitalocean_token=str(digitalocean_token),
        spaces_access_key=str(spaces_access_key),
        spaces_secret_key=str(spaces_secret_key),
        cloudflare_api_token_secret_name=str(cloudflare_api_token_secret_name),
        enable_traefik=parse_bool(str(enable_traefik) if enable_traefik else None),
        enable_cert_manager=parse_bool(
            str(enable_cert_manager) if enable_cert_manager else None
        ),
        enable_external_dns=parse_bool(
            str(enable_external_dns) if enable_external_dns else None
        ),
        enable_vault_eso=vault_eso_enabled,
        enable_cnpg=parse_bool(str(enable_cnpg) if enable_cnpg else None),
        dry_run=parse_bool(str(dry_run) if dry_run else None, default=False),
        runner_temp=runner_temp,
        github_env=github_env,
    )


def _mask_inputs(inputs: ResolvedInputs, mask: Mask) -> None:
    """Mask sensitive inputs before exporting."""
    mask(inputs.gitops_token)
    mask(inputs.digitalocean_token)
    mask(inputs.spaces_access_key)
    mask(inputs.spaces_secret_key)

    if inputs.vault_role_id:
        mask(inputs.vault_role_id)
    if inputs.vault_secret_id:
        mask(inputs.vault_secret_id)
    if inputs.vault_ca_certificate:
        mask(inputs.vault_ca_certificate)


def _build_env_vars(inputs: ResolvedInputs) -> dict[str, str]:
    """Build GITHUB_ENV variables from resolved inputs."""
    env_vars = {
        "CLUSTER_NAME": inputs.cluster_name,
        "ENVIRONMENT": inputs.environment,
        "REGION": inputs.region,
        "DOMAIN": inputs.domain,
        "ACME_EMAIL": inputs.acme_email,
        "GITOPS_REPOSITORY": inputs.gitops_repository,
        "GITOPS_BRANCH": inputs.gitops_branch,
        "GITOPS_TOKEN": inputs.gitops_token,
        "DIGITALOCEAN_TOKEN": inputs.digitalocean_token,
        "SPACES_ACCESS_KEY": inputs.spaces_access_key,
        "SPACES_SECRET_KEY": inputs.spaces_secret_key,
        "CLOUDFLARE_API_TOKEN_SECRET_NAME": inputs.cloudflare_api_token_secret_name,
        "ENABLE_TRAEFIK": str(inputs.enable_traefik).lower(),
        "ENABLE_CERT_MANAGER": str(inputs.enable_cert_manager).lower(),
        "ENABLE_EXTERNAL_DNS": str(inputs.enable_external_dns).lower(),
        "ENABLE_VAULT_ESO": str(inputs.enable_vault_eso).lower(),
        "ENABLE_CNPG": str(inputs.enable_cnpg).lower(),
        "DRY_RUN": str(inputs.dry_run).lower(),
        "RUNNER_TEMP": str(inputs.runner_temp),
        "GITHUB_ENV": str(inputs.github_env),
    }

    if inputs.node_pools is not None:
        env_vars["NODE_POOLS"] = json.dumps(inputs.node_pools)
    if inputs.kubernetes_version:
        env_vars["KUBERNETES_VERSION"] = inputs.kubernetes_version
    if inputs.vault_address:
        env_vars["VAULT_ADDRESS"] = inputs.vault_address
    if inputs.vault_role_id:
        env_vars["VAULT_ROLE_ID"] = inputs.vault_role_id
    if inputs.vault_secret_id:
        env_vars["VAULT_SECRET_ID"] = inputs.vault_secret_id
    if inputs.vault_ca_certificate:
        env_vars["VAULT_CA_CERTIFICATE"] = inputs.vault_ca_certificate

    return env_vars


def prepare_inputs(inputs: ResolvedInputs, mask: Mask = mask_secret) -> None:
    """Mask secrets and export resolved inputs to GITHUB_ENV.

    Parameters
    ----------
    inputs : ResolvedInputs
        Resolved inputs for the action.
    mask : Callable[[str], None], optional
        Callable used to mask secrets (default: mask_secret).

    Returns
    -------
    None
        Values are written to ``GITHUB_ENV``.

    Examples
    --------
    >>> raw = RawInputs(
    ...     cluster_name="preview-1",
    ...     environment="preview",
    ...     region="nyc1",
    ...     domain="example.test",
    ...     acme_email="admin@example.test",
    ...     gitops_repository="leynos/nile-valley-infra",
    ...     gitops_token="token",
    ...     vault_address="https://vault.example.test:8200",
    ...     vault_role_id="role",
    ...     vault_secret_id="secret",
    ...     digitalocean_token="do-token",
    ...     spaces_access_key="access",
    ...     spaces_secret_key="secret",
    ...     runner_temp=Path("/tmp"),
    ...     github_env=Path("/tmp/github-env"),
    ... )
    >>> prepare_inputs(_resolve_all_inputs(raw))
    """
    _mask_inputs(inputs, mask)
    env_vars = _build_env_vars(inputs)
    append_github_env(inputs.github_env, env_vars)
