"""Resolve and validate GitOps inputs for manifest commits.

This module converts raw CLI or environment values into a validated
``GitOpsInputs`` configuration used by the GitOps commit workflow. It
normalises types, applies defaults for local development, and raises
validation errors when required inputs are missing.

Examples
--------
>>> from scripts._gitops_inputs import RawGitOpsInputs, resolve_gitops_inputs
>>> inputs = resolve_gitops_inputs(
...     RawGitOpsInputs(
...         gitops_repository="leynos/nile-valley-infra",
...         gitops_token="token",
...         cluster_name="preview-1",
...     )
... )
>>> inputs.gitops_repository
'leynos/nile-valley-infra'
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts._gitops_errors import GitValidationError
from scripts._input_resolution import InputResolution, resolve_input
from scripts._infra_k8s import parse_bool

__all__ = ["GitOpsInputs", "RawGitOpsInputs", "resolve_gitops_inputs"]


@dataclass(frozen=True, slots=True)
class GitOpsInputs:
    """Inputs for GitOps commit.

    Attributes
    ----------
    gitops_repository, gitops_branch, gitops_token : str
        GitOps repository configuration values.
    cluster_name : str
        Cluster name used for manifest paths.
    render_output_dir, runner_temp, github_env : Path
        Paths for rendered manifests, working directories, and GITHUB_ENV.
    dry_run : bool
        Whether to skip the git push step.
    """

    # GitOps configuration
    gitops_repository: str
    gitops_branch: str
    gitops_token: str

    # Cluster identification
    cluster_name: str

    # Paths
    render_output_dir: Path
    runner_temp: Path
    github_env: Path

    # Options
    dry_run: bool


@dataclass(frozen=True, slots=True)
class RawGitOpsInputs:
    """Raw GitOps inputs from CLI or defaults.

    Attributes
    ----------
    gitops_repository, gitops_branch, gitops_token : str | None
        Raw GitOps repository inputs.
    cluster_name : str | None
        Raw cluster name input.
    render_output_dir, runner_temp, github_env : Path | None
        Raw path overrides.
    dry_run : str | None
        Raw dry-run flag.
    """

    gitops_repository: str | None = None
    gitops_branch: str | None = None
    gitops_token: str | None = None
    cluster_name: str | None = None
    render_output_dir: Path | None = None
    runner_temp: Path | None = None
    github_env: Path | None = None
    dry_run: str | None = None


def _to_path(value: Path | str | None, name: str | None = None) -> Path:
    """Coerce a string or Path to Path.

    Parameters
    ----------
    value : Path | str | None
        The value to coerce to a Path.
    name : str | None
        Descriptive name for the path value, used in error messages.

    Returns
    -------
    Path
        The coerced path value.

    Raises
    ------
    GitValidationError
        If value is None.
    """
    if value is None:
        label = name or "<unknown>"
        msg = f"Path value for '{label}' must not be None"
        raise GitValidationError(msg)
    return value if isinstance(value, Path) else Path(value)


def resolve_gitops_inputs(raw: RawGitOpsInputs) -> GitOpsInputs:
    """Resolve GitOps inputs from environment.

    Parameters
    ----------
    raw : RawGitOpsInputs
        Raw inputs from CLI or defaults.

    Returns
    -------
    GitOpsInputs
        Normalised inputs for GitOps operations.
    """
    gitops_repository = resolve_input(
        raw.gitops_repository,
        InputResolution(env_key="GITOPS_REPOSITORY", required=True),
    )
    gitops_branch = resolve_input(
        raw.gitops_branch, InputResolution(env_key="GITOPS_BRANCH", default="main")
    )
    gitops_token = resolve_input(
        raw.gitops_token, InputResolution(env_key="GITOPS_TOKEN", required=True)
    )

    cluster_name = resolve_input(
        raw.cluster_name, InputResolution(env_key="CLUSTER_NAME", required=True)
    )
    cluster_name_value = str(cluster_name)
    if not cluster_name_value.strip():
        msg = "Cluster name must not be empty"
        raise GitValidationError(msg)

    # resolve_input + InputResolution defaults for render_output_dir_raw,
    # runner_temp_raw, and github_env_raw are intentional local-dev/CI fallbacks
    # when GitHub Actions runner env keys are absent.
    render_output_dir_raw = resolve_input(
        raw.render_output_dir,
        InputResolution(
            env_key="RENDER_OUTPUT_DIR",
            default=Path("/tmp/rendered-manifests"),
            as_path=True,
        ),
    )
    runner_temp_raw = resolve_input(
        raw.runner_temp,
        InputResolution(env_key="RUNNER_TEMP", default=Path("/tmp"), as_path=True),
    )
    github_env_raw = resolve_input(
        raw.github_env,
        InputResolution(
            env_key="GITHUB_ENV",
            default=Path("/tmp/github-env-undefined"),
            as_path=True,
        ),
    )
    dry_run_raw = resolve_input(
        raw.dry_run, InputResolution(env_key="DRY_RUN", default="false")
    )

    return GitOpsInputs(
        gitops_repository=str(gitops_repository),
        gitops_branch=str(gitops_branch),
        gitops_token=str(gitops_token),
        cluster_name=cluster_name_value,
        render_output_dir=_to_path(render_output_dir_raw, "render_output_dir"),
        runner_temp=_to_path(runner_temp_raw, "runner_temp"),
        github_env=_to_path(github_env_raw, "github_env"),
        dry_run=parse_bool(cast("str | None", dry_run_raw), default=False),
    )
