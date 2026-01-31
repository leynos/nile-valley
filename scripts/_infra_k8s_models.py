"""Data models for nile-valley-infra-k8s orchestration.

These models provide a small, typed contract shared by the OpenTofu and action
helpers, keeping data flow explicit across module boundaries.

Examples
--------
>>> result = TofuResult(success=True, stdout="ok", stderr="", return_code=0)
>>> result.success
True
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SpacesBackendConfig:
    """Configuration for the DigitalOcean Spaces state backend.

    Attributes
    ----------
    bucket
        Spaces bucket name that stores the state file.
    region
        Spaces region identifier (e.g., ``nyc3``).
    endpoint
        S3-compatible endpoint URL for the Spaces region.
    access_key
        Spaces access key ID used for authentication.
    secret_key
        Spaces secret access key used for authentication.
    state_key
        Object key (path) for the state file within the bucket.

    Examples
    --------
    >>> config = SpacesBackendConfig(
    ...     bucket="nile-valley-terraform-state",
    ...     region="nyc3",
    ...     endpoint="https://nyc3.digitaloceanspaces.com",
    ...     access_key="AKIA...",
    ...     secret_key="secret",
    ...     state_key="clusters/dev/terraform.tfstate",
    ... )
    >>> config.state_key
    'clusters/dev/terraform.tfstate'
    """

    bucket: str
    region: str
    endpoint: str
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    state_key: str


@dataclass(frozen=True, slots=True)
class TofuResult:
    """Result of an OpenTofu command execution.

    Attributes
    ----------
    success
        Whether the command exited with status code ``0``.
    stdout
        Captured standard output (empty when not captured).
    stderr
        Captured standard error (empty when not captured).
    return_code
        Process exit status code returned by OpenTofu.

    Examples
    --------
    >>> TofuResult(success=True, stdout="ok", stderr="", return_code=0).success
    True
    """

    success: bool
    stdout: str
    stderr: str
    return_code: int
