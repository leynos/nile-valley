#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///
"""Prepare inputs for the nile-valley-infra-k8s GitHub Action.

This command resolves CLI and environment inputs, validates them, masks
sensitive values (via ``prepare_inputs`` and ``mask_secret``), and exports
resolved values to ``GITHUB_ENV`` for downstream steps.

Examples
--------
Run with explicit CLI overrides:

$ python scripts/prepare_infra_k8s_inputs.py --cluster-name preview-1 --region nyc1
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from cyclopts import App, Parameter
from scripts._input_resolution import _is_cyclopts_parameter
from scripts._prepare_infra_k8s_inputs import (
    RawInputs,
    ResolvedInputs,
    _resolve_all_inputs,
    prepare_inputs,
)

__all__ = [
    "RawInputs",
    "ResolvedInputs",
    "app",
    "prepare_inputs",
]

app = App(help="Prepare nile-valley-infra-k8s action inputs.")

CLUSTER_NAME_PARAM = Parameter(help="Cluster name override.")
ENVIRONMENT_PARAM = Parameter(help="Environment override.")
REGION_PARAM = Parameter(help="Region override.")
KUBERNETES_VERSION_PARAM = Parameter(help="Kubernetes version override.")
NODE_POOLS_PARAM = Parameter(help="Node pool JSON override.")
DOMAIN_PARAM = Parameter(help="Cluster domain override.")
ACME_EMAIL_PARAM = Parameter(help="ACME email override.")
GITOPS_REPOSITORY_PARAM = Parameter(help="GitOps repository override.")
GITOPS_BRANCH_PARAM = Parameter(help="GitOps branch override.")
GITOPS_TOKEN_PARAM = Parameter(help="GitOps token override.")
VAULT_ADDRESS_PARAM = Parameter(help="Vault address override.")
VAULT_ROLE_ID_PARAM = Parameter(help="Vault AppRole role ID override.")
VAULT_SECRET_ID_PARAM = Parameter(help="Vault AppRole secret ID override.")
VAULT_CA_CERTIFICATE_PARAM = Parameter(help="Vault CA certificate override.")
DIGITALOCEAN_TOKEN_PARAM = Parameter(help="DigitalOcean token override.")
SPACES_ACCESS_KEY_PARAM = Parameter(help="Spaces access key override.")
SPACES_SECRET_KEY_PARAM = Parameter(help="Spaces secret key override.")
CLOUDFLARE_API_TOKEN_SECRET_NAME_PARAM = Parameter(
    help="Cloudflare API token secret name override."
)
ENABLE_TRAEFIK_PARAM = Parameter(help="Enable Traefik flag override.")
ENABLE_CERT_MANAGER_PARAM = Parameter(help="Enable cert-manager flag override.")
ENABLE_EXTERNAL_DNS_PARAM = Parameter(help="Enable external-dns flag override.")
ENABLE_VAULT_ESO_PARAM = Parameter(help="Enable Vault ESO flag override.")
ENABLE_CNPG_PARAM = Parameter(help="Enable CNPG flag override.")
DRY_RUN_PARAM = Parameter(help="Dry-run flag override.")
RUNNER_TEMP_PARAM = Parameter(help="Runner temp directory override.")
GITHUB_ENV_PARAM = Parameter(help="GITHUB_ENV path override.")


def _collect_cli_values(values: Mapping[str, object]) -> RawInputs:
    """Collect CLI overrides into raw input values."""
    def _normalise_value(value: object | None) -> object | None:
        if value is None:
            return None
        if _is_cyclopts_parameter(value):
            return None
        return value

    def _get_str(key: str) -> str | None:
        return cast("str | None", _normalise_value(values.get(key)))

    def _get_path(key: str) -> Path | None:
        return cast("Path | None", _normalise_value(values.get(key)))

    return RawInputs(
        cluster_name=_get_str("cluster_name"),
        environment=_get_str("environment"),
        region=_get_str("region"),
        kubernetes_version=_get_str("kubernetes_version"),
        node_pools=_get_str("node_pools"),
        domain=_get_str("domain"),
        acme_email=_get_str("acme_email"),
        gitops_repository=_get_str("gitops_repository"),
        gitops_branch=_get_str("gitops_branch"),
        gitops_token=_get_str("gitops_token"),
        vault_address=_get_str("vault_address"),
        vault_role_id=_get_str("vault_role_id"),
        vault_secret_id=_get_str("vault_secret_id"),
        vault_ca_certificate=_get_str("vault_ca_certificate"),
        digitalocean_token=_get_str("digitalocean_token"),
        spaces_access_key=_get_str("spaces_access_key"),
        spaces_secret_key=_get_str("spaces_secret_key"),
        cloudflare_api_token_secret_name=_get_str(
            "cloudflare_api_token_secret_name"
        ),
        enable_traefik=_get_str("enable_traefik"),
        enable_cert_manager=_get_str("enable_cert_manager"),
        enable_external_dns=_get_str("enable_external_dns"),
        enable_vault_eso=_get_str("enable_vault_eso"),
        enable_cnpg=_get_str("enable_cnpg"),
        dry_run=_get_str("dry_run"),
        runner_temp=_get_path("runner_temp"),
        github_env=_get_path("github_env"),
    )


def _run_prepare_flow(raw: RawInputs) -> int:
    """Resolve and export inputs for downstream action steps."""
    resolved = _resolve_all_inputs(raw)
    prepare_inputs(resolved)
    print("Prepared nile-valley-infra-k8s inputs.")
    return 0


@app.command()
def main(
    cluster_name: str | None = CLUSTER_NAME_PARAM,
    environment: str | None = ENVIRONMENT_PARAM,
    region: str | None = REGION_PARAM,
    kubernetes_version: str | None = KUBERNETES_VERSION_PARAM,
    node_pools: str | None = NODE_POOLS_PARAM,
    domain: str | None = DOMAIN_PARAM,
    acme_email: str | None = ACME_EMAIL_PARAM,
    gitops_repository: str | None = GITOPS_REPOSITORY_PARAM,
    gitops_branch: str | None = GITOPS_BRANCH_PARAM,
    gitops_token: str | None = GITOPS_TOKEN_PARAM,
    vault_address: str | None = VAULT_ADDRESS_PARAM,
    vault_role_id: str | None = VAULT_ROLE_ID_PARAM,
    vault_secret_id: str | None = VAULT_SECRET_ID_PARAM,
    vault_ca_certificate: str | None = VAULT_CA_CERTIFICATE_PARAM,
    digitalocean_token: str | None = DIGITALOCEAN_TOKEN_PARAM,
    spaces_access_key: str | None = SPACES_ACCESS_KEY_PARAM,
    spaces_secret_key: str | None = SPACES_SECRET_KEY_PARAM,
    cloudflare_api_token_secret_name: str | None = CLOUDFLARE_API_TOKEN_SECRET_NAME_PARAM,
    enable_traefik: str | None = ENABLE_TRAEFIK_PARAM,
    enable_cert_manager: str | None = ENABLE_CERT_MANAGER_PARAM,
    enable_external_dns: str | None = ENABLE_EXTERNAL_DNS_PARAM,
    enable_vault_eso: str | None = ENABLE_VAULT_ESO_PARAM,
    enable_cnpg: str | None = ENABLE_CNPG_PARAM,
    dry_run: str | None = DRY_RUN_PARAM,
    runner_temp: Path | None = RUNNER_TEMP_PARAM,
    github_env: Path | None = GITHUB_ENV_PARAM,
) -> int:
    """Prepare inputs for the nile-valley-infra-k8s action (CLI overrides env)."""
    raw = _collect_cli_values(locals())
    return _run_prepare_flow(raw)


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(app())
