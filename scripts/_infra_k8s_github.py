"""GitHub Actions helpers for nile-valley-infra-k8s workflows.

This module centralizes parsing and file-writing helpers that mirror GitHub
Actions behaviour for ``GITHUB_ENV`` and ``GITHUB_OUTPUT`` files.

Examples
--------
>>> append_github_env(Path("/tmp/github-env"), {"CLUSTER_NAME": "demo"})
>>> parse_bool("true")
True
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO


def mask_secret(value: str, stream: Callable[[str], object] = print) -> None:
    """Emit the GitHub Actions secret masking command.

    Parameters
    ----------
    value
        Secret value to mask.
    stream
        Output stream for the masking command (defaults to ``print``).

    Returns
    -------
    None
        Writes one masking command per non-empty line in ``value``.

    Examples
    --------
    >>> mask_secret("token")
    """
    if not value:
        return
    for line in value.splitlines():
        if line:
            stream(f"::add-mask::{line}")


def parse_bool(value: str | None, *, default: bool = True) -> bool:
    """Parse a boolean-like string.

    Parameters
    ----------
    value
        Raw string value to parse.
    default
        Default value when ``value`` is ``None`` or blank.

    Returns
    -------
    bool
        Parsed boolean value.

    Examples
    --------
    >>> parse_bool("yes")
    True
    >>> parse_bool(None, default=False)
    False
    """
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("true", "1", "yes")


def parse_node_pools(value: str | None) -> list[dict[str, object]] | None:
    """Parse a node-pools JSON string.

    Parameters
    ----------
    value
        JSON-encoded node pool payload.

    Returns
    -------
    list[dict[str, object]] | None
        Parsed node pool structures, or ``None`` if input is blank.

    Examples
    --------
    >>> parse_node_pools('[{"name": "default", "node_count": 2}]')[0]["name"]
    'default'
    """
    if value is None or not value.strip():
        return None
    try:
        pools = json.loads(value)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON in node_pools: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(pools, list):
        msg = "node_pools must be a JSON array"
        raise TypeError(msg)
    return pools


def _choose_multiline_delimiter(value: str, base: str = "EOF") -> str:
    """Choose a heredoc delimiter that is not present in the value."""
    delimiter = base
    counter = 0
    while delimiter in value:
        counter += 1
        delimiter = f"{base}_{counter}"
    return delimiter


def _write_github_multiline(handle: TextIO, key: str, value: str) -> None:
    """Write a multiline GitHub Actions value using heredoc syntax."""
    delimiter = _choose_multiline_delimiter(value)
    handle.write(f"{key}<<{delimiter}\n")
    handle.write(f"{value}\n")
    handle.write(f"{delimiter}\n")


def _append_github_kv(target_file: Path, items: Mapping[str, str]) -> None:
    """Append key-value pairs to a GitHub Actions metadata file."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with target_file.open("a", encoding="utf-8") as handle:
        for key, value in items.items():
            if "\n" in value or "\r" in value:
                _write_github_multiline(handle, key, value)
            else:
                handle.write(f"{key}={value}\n")


def append_github_env(env_file: Path, variables: dict[str, str]) -> None:
    """Append environment variables to the ``GITHUB_ENV`` file.

    Parameters
    ----------
    env_file
        Path to the ``GITHUB_ENV`` file.
    variables
        Environment variables to append.

    Returns
    -------
    None
        Writes entries to the ``GITHUB_ENV`` file.

    Examples
    --------
    >>> append_github_env(Path("/tmp/env"), {"CLUSTER_NAME": "preview-1"})
    """
    _append_github_kv(env_file, variables)


def append_github_output(output_file: Path, outputs: dict[str, str]) -> None:
    """Append outputs to the ``GITHUB_OUTPUT`` file.

    Parameters
    ----------
    output_file
        Path to the ``GITHUB_OUTPUT`` file.
    outputs
        Outputs to append.

    Returns
    -------
    None
        Writes entries to the ``GITHUB_OUTPUT`` file.

    Examples
    --------
    >>> append_github_output(Path("/tmp/out"), {"cluster_id": "abc"})
    """
    _append_github_kv(output_file, outputs)
