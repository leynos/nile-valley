"""Manifest and validation helpers for nile-valley-infra-k8s."""

from __future__ import annotations

import json
import re
from pathlib import Path


def write_tfvars(path: Path, variables: dict[str, object]) -> None:
    """Write variables to a ``tfvars.json`` file.

    Parameters
    ----------
    path
        Destination path for the tfvars file.
    variables
        Variables to write.

    Returns
    -------
    None
        Writes the tfvars file to disk.

    Examples
    --------
    >>> write_tfvars(Path("/tmp/vars.tfvars.json"), {"cluster_name": "preview-1"})
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(variables, indent=2), encoding="utf-8")


def write_manifests(output_dir: Path, manifests: dict[str, str]) -> int:
    """Write rendered manifests to the output directory.

    Parameters
    ----------
    output_dir
        Base directory for manifest output.
    manifests
        Map of relative paths to YAML content.

    Returns
    -------
    int
        Number of manifests written.

    Examples
    --------
    >>> write_manifests(Path("/tmp/out"), {"ns.yaml": "apiVersion: v1"})
    1
    """
    count = 0
    output_root = output_dir.resolve()
    for rel_path, content in manifests.items():
        rel = Path(rel_path)
        if rel.is_absolute() or ".." in rel.parts:
            msg = f"Refusing to write manifest outside {output_dir}"
            raise ValueError(msg)
        dest = output_dir / rel
        if not dest.resolve().is_relative_to(output_root):
            msg = f"Refusing to write manifest outside {output_dir}"
            raise ValueError(msg)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        count += 1
    return count


def validate_cluster_name(name: str) -> str:
    """Validate and normalize a cluster name.

    Parameters
    ----------
    name
        Cluster name to validate.

    Returns
    -------
    str
        Normalized cluster name.

    Raises
    ------
    ValueError
        If the name is invalid.

    Examples
    --------
    >>> validate_cluster_name(" Preview-1 ")
    'preview-1'
    """
    name = name.strip().lower()
    if not name:
        msg = "cluster_name must not be blank"
        raise ValueError(msg)
    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", name):
        msg = "cluster_name must contain only lowercase letters, numbers, and hyphens"
        raise ValueError(msg)
    return name
