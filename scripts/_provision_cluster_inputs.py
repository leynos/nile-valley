"""Resolve inputs and build tfvars for cluster provisioning.

This module converts CLI or environment values into a validated
``ProvisionInputs`` configuration, then derives backend configuration and
tfvars for the OpenTofu provisioning flow. It centralizes validation so
the provisioning script can focus on execution.

Examples
--------
>>> from pathlib import Path
>>> from scripts._provision_cluster_inputs import (
...     RawProvisionInputs,
...     resolve_provision_inputs,
... )
>>> inputs = resolve_provision_inputs(
...     RawProvisionInputs(
...         cluster_name="preview-1",
...         environment="preview",
...         region="nyc1",
...         spaces_bucket="nile-valley-tofu-state",
...         spaces_region="nyc3",
...         spaces_access_key="access",
...         spaces_secret_key="secret",
...         runner_temp=Path("/tmp"),
...         github_env=Path("/tmp/env"),
...     )
... )
>>> inputs.cluster_name
'preview-1'
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts._input_resolution import (
    InputResolution,
    _is_cyclopts_parameter,
    resolve_input,
)
from scripts._infra_k8s import SpacesBackendConfig, parse_bool, parse_node_pools


@dataclass(frozen=True, slots=True)
class ProvisionInputs:
    """Inputs for cluster provisioning.

    Attributes
    ----------
    cluster_name : str
        Cluster name identifier.
    environment : str
        Environment name for the cluster.
    region : str
        Cloud region for provisioning.
    kubernetes_version : str | None
        Optional Kubernetes version override.
    node_pools : str | None
        Optional node pool JSON payload.
    spaces_bucket : str
        Spaces bucket for OpenTofu state.
    spaces_region : str
        Spaces region for state storage.
    spaces_access_key : str
        Access key for the Spaces backend.
    spaces_secret_key : str
        Secret key for the Spaces backend.
    runner_temp : Path
        Directory for temporary working files.
    github_env : Path
        Path to the GitHub Actions environment file.
    dry_run : bool
        Whether to skip apply and only plan.
    """

    # Cluster configuration
    cluster_name: str
    environment: str
    region: str
    kubernetes_version: str | None
    node_pools: str | None

    # Backend configuration
    spaces_bucket: str
    spaces_region: str
    spaces_access_key: str
    spaces_secret_key: str

    # Paths and options
    runner_temp: Path
    github_env: Path
    dry_run: bool


@dataclass(frozen=True, slots=True)
class RawProvisionInputs:
    """Raw provisioning inputs from CLI or defaults.

    Attributes
    ----------
    cluster_name : str | None
        Raw cluster name override.
    environment : str | None
        Raw environment override.
    region : str | None
        Raw region override.
    kubernetes_version : str | None
        Raw Kubernetes version override.
    node_pools : str | None
        Raw node pools payload.
    spaces_bucket : str | None
        Raw Spaces bucket override.
    spaces_region : str | None
        Raw Spaces region override.
    spaces_access_key : str | None
        Raw Spaces access key override.
    spaces_secret_key : str | None
        Raw Spaces secret key override.
    runner_temp : Path | None
        Raw runner temp path override.
    github_env : Path | None
        Raw GitHub Actions env file override.
    dry_run : str | None
        Raw dry-run flag.
    """

    cluster_name: str | None = None
    environment: str | None = None
    region: str | None = None
    kubernetes_version: str | None = None
    node_pools: str | None = None
    spaces_bucket: str | None = None
    spaces_region: str | None = None
    spaces_access_key: str | None = None
    spaces_secret_key: str | None = None
    runner_temp: Path | None = None
    github_env: Path | None = None
    dry_run: str | None = None


def _with_override(
    value: str | Path | None,
    resolution: InputResolution,
) -> str | Path | None:
    """Return the CLI override when present, otherwise resolve from environment."""
    if value is not None and not _is_cyclopts_parameter(value):
        return value
    return resolve_input(None, resolution)


def _to_path(value: Path | str) -> Path:
    """Normalize string and Path values into Path instances."""
    return value if isinstance(value, Path) else Path(value)


def _resolve_cluster_inputs(
    raw: RawProvisionInputs,
) -> tuple[str, str, str, str | None, str | None]:
    """Resolve cluster configuration inputs."""
    cluster_name = _with_override(
        raw.cluster_name, InputResolution(env_key="CLUSTER_NAME", required=True)
    )
    environment = _with_override(
        raw.environment, InputResolution(env_key="ENVIRONMENT", required=True)
    )
    region = _with_override(raw.region, InputResolution(env_key="REGION", required=True))
    kubernetes_version = _with_override(
        raw.kubernetes_version, InputResolution(env_key="KUBERNETES_VERSION")
    )
    node_pools = _with_override(raw.node_pools, InputResolution(env_key="NODE_POOLS"))
    return (
        str(cluster_name),
        str(environment),
        str(region),
        str(kubernetes_version) if kubernetes_version else None,
        str(node_pools) if node_pools else None,
    )


def _resolve_spaces_config(
    raw: RawProvisionInputs,
) -> tuple[str, str, str, str]:
    """Resolve Spaces backend configuration inputs."""
    spaces_bucket = _with_override(
        raw.spaces_bucket,
        InputResolution(env_key="SPACES_BUCKET", default="nile-valley-tofu-state"),
    )
    spaces_region = _with_override(
        raw.spaces_region, InputResolution(env_key="SPACES_REGION", default="lon1")
    )
    spaces_access_key = _with_override(
        raw.spaces_access_key,
        InputResolution(env_key="SPACES_ACCESS_KEY", required=True),
    )
    spaces_secret_key = _with_override(
        raw.spaces_secret_key,
        InputResolution(env_key="SPACES_SECRET_KEY", required=True),
    )
    return (
        str(spaces_bucket),
        str(spaces_region),
        str(spaces_access_key),
        str(spaces_secret_key),
    )


def _resolve_execution_config(
    raw: RawProvisionInputs,
) -> tuple[Path, Path, bool]:
    """Resolve execution configuration inputs."""
    # RUNNER_TEMP/GITHUB_ENV/DRY_RUN InputResolution defaults (Path("/tmp"),
    # Path("/tmp/github-env-undefined"), and "false") are intentional
    # local-dev/test fallbacks to avoid hard failures when those env keys are
    # absent; production usage should set the env_key values explicitly.
    runner_temp_raw = _with_override(
        raw.runner_temp,
        InputResolution(env_key="RUNNER_TEMP", default=Path("/tmp"), as_path=True),
    )
    github_env_raw = _with_override(
        raw.github_env,
        InputResolution(
            env_key="GITHUB_ENV",
            default=Path("/tmp/github-env-undefined"),
            as_path=True,
        ),
    )
    dry_run_raw = _with_override(
        raw.dry_run, InputResolution(env_key="DRY_RUN", default="false")
    )
    assert runner_temp_raw is not None, (
        "_resolve_execution_config expected _with_override to supply RUNNER_TEMP "
        "before _to_path conversion."
    )
    assert github_env_raw is not None, (
        "_resolve_execution_config expected _with_override to supply GITHUB_ENV "
        "before _to_path conversion."
    )
    return (
        _to_path(runner_temp_raw),
        _to_path(github_env_raw),
        parse_bool(str(dry_run_raw) if dry_run_raw else None, default=False),
    )


def resolve_provision_inputs(raw: RawProvisionInputs) -> ProvisionInputs:
    """Resolve provisioning inputs from CLI overrides with environment fallbacks."""

    (
        cluster_name,
        environment,
        region,
        kubernetes_version,
        node_pools,
    ) = _resolve_cluster_inputs(raw)
    (
        spaces_bucket,
        spaces_region,
        spaces_access_key,
        spaces_secret_key,
    ) = _resolve_spaces_config(raw)
    runner_temp, github_env, dry_run = _resolve_execution_config(raw)

    return ProvisionInputs(
        cluster_name=cluster_name,
        environment=environment,
        region=region,
        kubernetes_version=kubernetes_version,
        node_pools=node_pools,
        spaces_bucket=spaces_bucket,
        spaces_region=spaces_region,
        spaces_access_key=spaces_access_key,
        spaces_secret_key=spaces_secret_key,
        runner_temp=runner_temp,
        github_env=github_env,
        dry_run=dry_run,
    )


def build_backend_config(inputs: ProvisionInputs) -> SpacesBackendConfig:
    """Build the OpenTofu backend configuration for Spaces state storage.

    Parameters
    ----------
    inputs : ProvisionInputs
        Normalized provisioning inputs.

    Returns
    -------
    SpacesBackendConfig
        Backend configuration derived from the inputs.
    """
    endpoint = f"https://{inputs.spaces_region}.digitaloceanspaces.com"
    state_key = f"clusters/{inputs.cluster_name}/terraform.tfstate"

    return SpacesBackendConfig(
        bucket=inputs.spaces_bucket,
        region=inputs.spaces_region,
        endpoint=endpoint,
        access_key=inputs.spaces_access_key,
        secret_key=inputs.spaces_secret_key,
        state_key=state_key,
    )


def build_tfvars(inputs: ProvisionInputs) -> dict[str, object]:
    """Build OpenTofu variables for cluster provisioning.

    Parameters
    ----------
    inputs : ProvisionInputs
        Normalized provisioning inputs.

    Returns
    -------
    dict[str, object]
        Mapping of OpenTofu variables to render into tfvars.
    """
    variables: dict[str, object] = {
        "cluster_name": inputs.cluster_name,
        "environment": inputs.environment,
        "region": inputs.region,
    }

    if inputs.kubernetes_version:
        variables["kubernetes_version"] = inputs.kubernetes_version

    if inputs.node_pools is not None:
        node_pools = parse_node_pools(inputs.node_pools)
        if node_pools is not None:
            variables["node_pools"] = node_pools

    return variables
