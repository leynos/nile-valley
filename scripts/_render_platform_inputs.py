"""Resolve platform render inputs and build OpenTofu tfvars.

This module resolves environment and CLI inputs into structured configuration
for platform manifest rendering and generates OpenTofu variables for the
platform modules. It assumes inputs are prepared by the action input
preparation step and that required environment variables are available.

Usage:
    python scripts/render_platform_manifests.py

Examples:
    >>> raw = RawRenderInputs(
    ...     cluster_name="preview-1",
    ...     domain="example.test",
    ...     acme_email="ops@example.test",
    ... )
    >>> inputs = resolve_render_inputs(raw)
    >>> build_render_tfvars(inputs)["cluster_name"]
    'preview-1'
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts._input_resolution import InputResolution, resolve_input
from scripts._infra_k8s import parse_bool


@dataclass(frozen=True, slots=True)
class RenderInputs:
    """Inputs for platform manifest rendering.

    Attributes
    ----------
    cluster_name, domain, acme_email, cloudflare_api_token_secret_name : str
        Core platform configuration values.
    vault_address, vault_role_id, vault_secret_id, vault_ca_certificate : str | None
        Vault configuration values.
    enable_traefik, enable_cert_manager, enable_external_dns : bool
        Feature flags for platform components.
    enable_vault_eso, enable_cnpg : bool
        Feature flags for Vault ESO and CNPG.
    runner_temp, output_dir, github_env : Path
        Paths for runtime artifacts and exports.
    """

    # Core configuration
    cluster_name: str
    domain: str
    acme_email: str
    cloudflare_api_token_secret_name: str

    # Vault configuration
    vault_address: str | None
    vault_role_id: str | None
    vault_secret_id: str | None
    vault_ca_certificate: str | None

    # Feature flags
    enable_traefik: bool
    enable_cert_manager: bool
    enable_external_dns: bool
    enable_vault_eso: bool
    enable_cnpg: bool

    # Paths
    runner_temp: Path
    output_dir: Path
    github_env: Path


@dataclass(frozen=True, slots=True)
class RawRenderInputs:
    """Raw render inputs from CLI or defaults.

    Attributes
    ----------
    cluster_name, domain, acme_email, cloudflare_api_token_secret_name : str | None
        Raw core configuration values.
    vault_address, vault_role_id, vault_secret_id, vault_ca_certificate : str | None
        Raw Vault configuration values.
    enable_traefik, enable_cert_manager, enable_external_dns : str | None
        Raw feature flag values.
    enable_vault_eso, enable_cnpg : str | None
        Raw Vault ESO and CNPG flags.
    runner_temp, output_dir, github_env : Path | None
        Raw path overrides.
    """

    cluster_name: str | None = None
    domain: str | None = None
    acme_email: str | None = None
    cloudflare_api_token_secret_name: str | None = None
    vault_address: str | None = None
    vault_role_id: str | None = None
    vault_secret_id: str | None = None
    vault_ca_certificate: str | None = None
    enable_traefik: str | None = None
    enable_cert_manager: str | None = None
    enable_external_dns: str | None = None
    enable_vault_eso: str | None = None
    enable_cnpg: str | None = None
    runner_temp: Path | None = None
    output_dir: Path | None = None
    github_env: Path | None = None


def _missing_vault_auth_fields(
    *,
    address: str | None,
    role_id: str | None,
    secret_id: str | None,
) -> list[str]:
    """Return the list of required Vault ESO auth env keys that are unset."""
    required = (
        ("VAULT_ADDRESS", address),
        ("VAULT_ROLE_ID", role_id),
        ("VAULT_SECRET_ID", secret_id),
    )
    return [name for name, value in required if not value]


def _resolve_core_config(raw: RawRenderInputs) -> tuple[str, str, str, str]:
    """Resolve core platform configuration inputs."""
    cluster_name_raw = resolve_input(
        raw.cluster_name, InputResolution(env_key="CLUSTER_NAME", required=True)
    )
    domain_raw = resolve_input(
        raw.domain, InputResolution(env_key="DOMAIN", required=True)
    )
    acme_email_raw = resolve_input(
        raw.acme_email, InputResolution(env_key="ACME_EMAIL", required=True)
    )
    cloudflare_secret_raw = resolve_input(
        raw.cloudflare_api_token_secret_name,
        InputResolution(
            env_key="CLOUDFLARE_API_TOKEN_SECRET_NAME",
            default="cloudflare-api-token",
        ),
    )
    return (
        cast("str", cluster_name_raw),
        cast("str", domain_raw),
        cast("str", acme_email_raw),
        cast("str", cloudflare_secret_raw),
    )


def _resolve_vault_config(
    raw: RawRenderInputs,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Resolve vault configuration inputs."""
    vault_address_raw = resolve_input(
        raw.vault_address, InputResolution(env_key="VAULT_ADDRESS")
    )
    vault_role_id_raw = resolve_input(
        raw.vault_role_id, InputResolution(env_key="VAULT_ROLE_ID")
    )
    vault_secret_id_raw = resolve_input(
        raw.vault_secret_id, InputResolution(env_key="VAULT_SECRET_ID")
    )
    vault_ca_cert_raw = resolve_input(
        raw.vault_ca_certificate, InputResolution(env_key="VAULT_CA_CERTIFICATE")
    )
    return (
        cast("str | None", vault_address_raw),
        cast("str | None", vault_role_id_raw),
        cast("str | None", vault_secret_id_raw),
        cast("str | None", vault_ca_cert_raw),
    )


def _resolve_feature_flags(raw: RawRenderInputs) -> tuple[str, str, str, str, str]:
    """Resolve feature flag inputs."""
    enable_traefik = resolve_input(
        raw.enable_traefik,
        InputResolution(env_key="ENABLE_TRAEFIK", default="true"),
    )
    enable_cert_manager = resolve_input(
        raw.enable_cert_manager,
        InputResolution(env_key="ENABLE_CERT_MANAGER", default="true"),
    )
    enable_external_dns = resolve_input(
        raw.enable_external_dns,
        InputResolution(env_key="ENABLE_EXTERNAL_DNS", default="true"),
    )
    enable_vault_eso = resolve_input(
        raw.enable_vault_eso,
        InputResolution(env_key="ENABLE_VAULT_ESO", default="true"),
    )
    enable_cnpg = resolve_input(
        raw.enable_cnpg,
        InputResolution(env_key="ENABLE_CNPG", default="true"),
    )
    return (
        cast("str", enable_traefik),
        cast("str", enable_cert_manager),
        cast("str", enable_external_dns),
        cast("str", enable_vault_eso),
        cast("str", enable_cnpg),
    )


def _resolve_paths(raw: RawRenderInputs) -> tuple[Path, Path, Path]:
    """Resolve path inputs for rendering."""
    # RUNNER_TEMP/RENDER_OUTPUT_DIR/GITHUB_ENV defaults use the system temp
    # directory as a safe fallback for local development and CI, avoiding hard
    # failures when the env_key values are not provided.
    temp_root = Path(tempfile.gettempdir())
    runner_temp_raw = resolve_input(
        raw.runner_temp,
        InputResolution(env_key="RUNNER_TEMP", default=temp_root, as_path=True),
    )
    output_dir_raw = resolve_input(
        raw.output_dir,
        InputResolution(
            env_key="RENDER_OUTPUT_DIR",
            default=temp_root / "rendered-manifests",
            as_path=True,
        ),
    )
    github_env_raw = resolve_input(
        raw.github_env,
        InputResolution(
            env_key="GITHUB_ENV",
            default=temp_root / "github-env-undefined",
            as_path=True,
        ),
    )
    return (
        cast("Path", runner_temp_raw),
        cast("Path", output_dir_raw),
        cast("Path", github_env_raw),
    )


def resolve_render_inputs(raw: RawRenderInputs) -> RenderInputs:
    """Resolve rendering inputs from raw CLI or environment values.

    Parameters
    ----------
    raw : RawRenderInputs
        Raw inputs from CLI overrides or environment.

    Returns
    -------
    RenderInputs
        Normalized inputs for platform manifest rendering.

    Examples
    --------
    >>> resolve_render_inputs(
    ...     RawRenderInputs(
    ...         cluster_name="preview-1",
    ...         domain="example.test",
    ...         acme_email="ops@example.test",
    ...     )
    ... )  # doctest: +ELLIPSIS
    RenderInputs(cluster_name='preview-1', domain='example.test', acme_email='ops@example.test', ...)
    """
    (
        cluster_name_raw,
        domain_raw,
        acme_email_raw,
        cloudflare_secret_raw,
    ) = _resolve_core_config(raw)
    traefik_raw, cert_manager_raw, external_dns_raw, vault_eso_raw, cnpg_raw = (
        _resolve_feature_flags(raw)
    )
    (
        vault_address_raw,
        vault_role_id_raw,
        vault_secret_id_raw,
        vault_ca_cert_raw,
    ) = _resolve_vault_config(raw)
    runner_temp_raw, output_dir_raw, github_env_raw = _resolve_paths(raw)

    vault_eso_enabled = parse_bool(str(vault_eso_raw))
    missing = _missing_vault_auth_fields(
        address=vault_address_raw,
        role_id=vault_role_id_raw,
        secret_id=vault_secret_id_raw,
    )
    if vault_eso_enabled and missing:
        msg = f"ENABLE_VAULT_ESO=true requires {', '.join(missing)} to be set."
        raise ValueError(msg)

    return RenderInputs(
        cluster_name=str(cluster_name_raw),
        domain=str(domain_raw),
        acme_email=str(acme_email_raw),
        cloudflare_api_token_secret_name=str(cloudflare_secret_raw),
        vault_address=str(vault_address_raw) if vault_address_raw else None,
        vault_role_id=str(vault_role_id_raw) if vault_role_id_raw else None,
        vault_secret_id=str(vault_secret_id_raw) if vault_secret_id_raw else None,
        vault_ca_certificate=str(vault_ca_cert_raw) if vault_ca_cert_raw else None,
        enable_traefik=parse_bool(str(traefik_raw)),
        enable_cert_manager=parse_bool(str(cert_manager_raw)),
        enable_external_dns=parse_bool(str(external_dns_raw)),
        enable_vault_eso=vault_eso_enabled,
        enable_cnpg=parse_bool(str(cnpg_raw)),
        runner_temp=runner_temp_raw,
        output_dir=output_dir_raw,
        github_env=github_env_raw,
    )


def build_render_tfvars(inputs: RenderInputs) -> dict[str, object]:
    """Build OpenTofu variables for platform rendering.

    Parameters
    ----------
    inputs : RenderInputs
        Normalized render inputs.

    Returns
    -------
    dict[str, object]
        OpenTofu variables for the platform render module.

    Examples
    --------
    >>> from pathlib import Path
    >>> workspace = Path("workspace")
    >>> inputs = RenderInputs(
    ...     cluster_name="preview-1",
    ...     domain="example.test",
    ...     acme_email="ops@example.test",
    ...     cloudflare_api_token_secret_name="cloudflare-api-token",
    ...     vault_address=None,
    ...     vault_role_id=None,
    ...     vault_secret_id=None,
    ...     vault_ca_certificate=None,
    ...     enable_traefik=True,
    ...     enable_cert_manager=True,
    ...     enable_external_dns=True,
    ...     enable_vault_eso=False,
    ...     enable_cnpg=True,
    ...     runner_temp=workspace,
    ...     output_dir=workspace / "rendered",
    ...     github_env=workspace / "github-env",
    ... )
    >>> build_render_tfvars(inputs)["cluster_name"]
    'preview-1'
    """
    variables: dict[str, object] = {
        "cluster_name": inputs.cluster_name,
        "domain": inputs.domain,
        "acme_email": inputs.acme_email,
        "cloudflare_api_token_secret_name": inputs.cloudflare_api_token_secret_name,
        "traefik_enabled": inputs.enable_traefik,
        "cert_manager_enabled": inputs.enable_cert_manager,
        "external_dns_enabled": inputs.enable_external_dns,
        "vault_eso_enabled": inputs.enable_vault_eso,
        "cnpg_enabled": inputs.enable_cnpg,
    }

    if inputs.enable_vault_eso:
        if inputs.vault_address:
            variables["vault_address"] = inputs.vault_address
        if inputs.vault_role_id:
            variables["vault_approle_role_id"] = inputs.vault_role_id
        if inputs.vault_secret_id:
            variables["vault_approle_secret_id"] = inputs.vault_secret_id
        if inputs.vault_ca_certificate:
            variables["vault_ca_bundle_pem"] = inputs.vault_ca_certificate

    return variables
