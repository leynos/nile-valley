"""OpenTofu orchestration helpers for nile-valley-infra-k8s."""

from __future__ import annotations

import json
import os
import subprocess
from collections import abc as cabc
from pathlib import Path

from scripts._infra_k8s_errors import TofuCommandError
from scripts._infra_k8s_models import SpacesBackendConfig, TofuResult


def _validate_command_args(args: list[str]) -> None:
    """Validate OpenTofu CLI arguments for safe execution."""
    for arg in args:
        if not isinstance(arg, str):
            msg = f"OpenTofu argument must be a string, got {type(arg).__name__}"
            raise TypeError(msg)
        if any(char in arg for char in ("\x00", "\n", "\r")):
            msg = "OpenTofu argument contains an invalid control character"
            raise ValueError(msg)


def run_tofu(
    args: list[str],
    cwd: Path,
    env: cabc.Mapping[str, str] | None = None,
    *,
    capture_output: bool = True,
) -> TofuResult:
    """Execute an OpenTofu command and return the result.

    Parameters
    ----------
    args
        Command arguments (without the ``tofu`` prefix).
    cwd
        Working directory for the command.
    env
        Environment variables to set for the command.
    capture_output
        Whether to capture stdout and stderr.

    Returns
    -------
    TofuResult
        Result containing success status, output, and return code.

    Examples
    --------
    >>> from pathlib import Path
    >>> result = run_tofu(["version"], Path("."))
    >>> result.success
    True
    >>> result.return_code
    0
    """
    cmd = ["tofu", *args]
    merged_env = {**os.environ, **(env or {})}

    # List-based invocation without ``shell=True`` avoids injection risks.
    _validate_command_args(cmd)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=capture_output,
        text=True,
        check=False,
    )

    return TofuResult(
        success=result.returncode == 0,
        stdout=result.stdout if capture_output else "",
        stderr=result.stderr if capture_output else "",
        return_code=result.returncode,
    )


def tofu_init(
    cwd: Path,
    backend_config: SpacesBackendConfig,
    backend_config_file: Path,
) -> TofuResult:
    """Initialize OpenTofu with backend configuration.

    Parameters
    ----------
    cwd
        OpenTofu configuration directory.
    backend_config
        Backend configuration for state storage.
    backend_config_file
        Path to the ``.tfbackend`` file.

    Returns
    -------
    TofuResult
        Result of the init command.

    Examples
    --------
    >>> from pathlib import Path
    >>> config = SpacesBackendConfig(
    ...     bucket="nile-valley-terraform-state",
    ...     region="nyc3",
    ...     endpoint="https://nyc3.digitaloceanspaces.com",
    ...     access_key="AKIA...",
    ...     secret_key="secret",
    ...     state_key="clusters/dev/terraform.tfstate",
    ... )
    >>> result = tofu_init(Path("infra"), config, Path("backend.tfbackend"))
    >>> result.success
    True
    """
    args = [
        "init",
        f"-backend-config={backend_config_file}",
        f"-backend-config=region={backend_config.region}",
        f"-backend-config=endpoint={backend_config.endpoint}",
        f"-backend-config=key={backend_config.state_key}",
        "-input=false",
    ]
    backend_env = {
        "AWS_ACCESS_KEY_ID": backend_config.access_key,
        "AWS_SECRET_ACCESS_KEY": backend_config.secret_key,
    }
    return run_tofu(args, cwd, env=backend_env)


def tofu_plan(cwd: Path, var_file: Path | None = None) -> TofuResult:
    """Run ``tofu plan``.

    Parameters
    ----------
    cwd
        OpenTofu configuration directory.
    var_file
        Optional path to a tfvars file.

    Returns
    -------
    TofuResult
        Result of the plan command.

    Examples
    --------
    >>> from pathlib import Path
    >>> tofu_plan(Path("infra")).success
    True
    >>> tofu_plan(Path("infra"), var_file=Path("dev.tfvars")).success
    True
    """
    args = ["plan", "-input=false"]
    if var_file:
        args.append(f"-var-file={var_file}")
    return run_tofu(args, cwd)


def tofu_apply(
    cwd: Path,
    var_file: Path | None = None,
    *,
    auto_approve: bool = True,
) -> TofuResult:
    """Run ``tofu apply``.

    Parameters
    ----------
    cwd
        OpenTofu configuration directory.
    var_file
        Optional path to a tfvars file.
    auto_approve
        Whether to auto-approve the apply.

    Returns
    -------
    TofuResult
        Result of the apply command.

    Examples
    --------
    >>> from pathlib import Path
    >>> tofu_apply(Path("infra")).success
    True
    >>> tofu_apply(Path("infra"), var_file=Path("dev.tfvars")).success
    True
    """
    args = ["apply", "-input=false"]
    if auto_approve:
        args.append("-auto-approve")
    if var_file:
        args.append(f"-var-file={var_file}")
    return run_tofu(args, cwd)


def tofu_output(cwd: Path, name: str | None = None) -> object:
    """Retrieve OpenTofu outputs as JSON.

    Parameters
    ----------
    cwd
        OpenTofu configuration directory.
    name
        Specific output name to retrieve.

    Returns
    -------
    object
        Parsed JSON output. If ``name`` is specified, returns the raw value.

    Examples
    --------
    >>> from pathlib import Path
    >>> outputs = tofu_output(Path("infra"))
    >>> outputs["cluster_name"]["value"]
    'nile-valley-dev'
    >>> tofu_output(Path("infra"), "cluster_name")
    'nile-valley-dev'
    """
    args = ["output", "-json"]
    if name:
        args.append(name)
    result = run_tofu(args, cwd)

    if not result.success:
        msg = (
            "tofu output failed "
            f"(cwd={cwd}, return_code={result.return_code}): {result.stderr}"
        )
        raise TofuCommandError(msg)

    return json.loads(result.stdout)
