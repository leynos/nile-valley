#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///
"""Publish outputs for the nile-valley-infra-k8s GitHub Action.

This script resolves action outputs from environment variables, writes them to
``GITHUB_OUTPUT``, and performs a final secret masking pass.

Examples
--------
>>> python scripts/publish_infra_k8s_outputs.py --github-output /tmp/output
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cyclopts import App, Parameter
from scripts._input_resolution import InputResolution, resolve_input
from scripts._infra_k8s import append_github_output, mask_secret

app = App(help="Publish nile-valley-infra-k8s action outputs.")

CLUSTER_NAME_PARAM = Parameter(help="Cluster name output override.")
CLUSTER_ID_PARAM = Parameter(help="Cluster ID output override.")
CLUSTER_ENDPOINT_PARAM = Parameter(help="Cluster endpoint output override.")
GITOPS_COMMIT_SHA_PARAM = Parameter(help="GitOps commit SHA output override.")
RENDERED_MANIFEST_COUNT_PARAM = Parameter(
    help="Rendered manifest count output override."
)
GITHUB_OUTPUT_PARAM = Parameter(help="GITHUB_OUTPUT path override.")


@dataclass(frozen=True, slots=True)
class OutputValues:
    """Values to publish as action outputs.

    Attributes
    ----------
    cluster_name : str | None
        Cluster name output value.
    cluster_id : str | None
        Cluster ID output value.
    cluster_endpoint : str | None
        Cluster API endpoint output value.
    gitops_commit_sha : str | None
        GitOps commit SHA output value.
    rendered_manifest_count : str | None
        Count of rendered manifests.
    """

    cluster_name: str | None
    cluster_id: str | None
    cluster_endpoint: str | None
    gitops_commit_sha: str | None
    rendered_manifest_count: str | None


@dataclass(frozen=True, slots=True)
class RawOutputValues:
    """Raw output values from CLI or defaults.

    Attributes
    ----------
    cluster_name : str | None
        Cluster name override for ``CLUSTER_NAME``.
    cluster_id : str | None
        Cluster ID override for ``CLUSTER_ID``.
    cluster_endpoint : str | None
        Cluster endpoint override for ``CLUSTER_ENDPOINT``.
    gitops_commit_sha : str | None
        GitOps commit SHA override for ``GITOPS_COMMIT_SHA``.
    rendered_manifest_count : str | None
        Rendered manifest count override for ``RENDERED_MANIFEST_COUNT``.
    """

    cluster_name: str | None = None
    cluster_id: str | None = None
    cluster_endpoint: str | None = None
    gitops_commit_sha: str | None = None
    rendered_manifest_count: str | None = None


def resolve_output_values(raw: RawOutputValues) -> OutputValues:
    """Resolve output values from environment.

    Parameters
    ----------
    raw : RawOutputValues
        Raw output values from CLI or defaults.

    Returns
    -------
    OutputValues
        Normalized output values.

    Examples
    --------
    >>> resolve_output_values(RawOutputValues())
    OutputValues(
        cluster_name=None,
        cluster_id=None,
        cluster_endpoint=None,
        gitops_commit_sha=None,
        rendered_manifest_count=None,
    )
    """
    cluster_name = resolve_input(
        raw.cluster_name, InputResolution(env_key="CLUSTER_NAME")
    )
    cluster_id = resolve_input(raw.cluster_id, InputResolution(env_key="CLUSTER_ID"))
    cluster_endpoint = resolve_input(
        raw.cluster_endpoint, InputResolution(env_key="CLUSTER_ENDPOINT")
    )
    gitops_commit_sha = resolve_input(
        raw.gitops_commit_sha, InputResolution(env_key="GITOPS_COMMIT_SHA")
    )
    rendered_manifest_count = resolve_input(
        raw.rendered_manifest_count,
        InputResolution(env_key="RENDERED_MANIFEST_COUNT"),
    )

    return OutputValues(
        cluster_name=str(cluster_name) if cluster_name else None,
        cluster_id=str(cluster_id) if cluster_id else None,
        cluster_endpoint=str(cluster_endpoint) if cluster_endpoint else None,
        gitops_commit_sha=str(gitops_commit_sha) if gitops_commit_sha else None,
        rendered_manifest_count=(
            str(rendered_manifest_count) if rendered_manifest_count else None
        ),
    )


def publish_outputs(values: OutputValues, github_output: Path) -> None:
    """Write outputs to GITHUB_OUTPUT file.

    Parameters
    ----------
    values : OutputValues
        Output values to publish.
    github_output : Path
        Path to the GITHUB_OUTPUT file.

    Returns
    -------
    None
        Values are written to ``GITHUB_OUTPUT``.

    Examples
    --------
    >>> publish_outputs(OutputValues(None, None, None, None, None), Path("/tmp/out"))
    """
    outputs = {
        key: value
        for key, value in {
            "cluster_name": values.cluster_name,
            "cluster_id": values.cluster_id,
            "cluster_endpoint": values.cluster_endpoint,
            "gitops_commit_sha": values.gitops_commit_sha,
            "rendered_manifest_count": values.rendered_manifest_count,
        }.items()
        if value
    }

    if outputs:
        append_github_output(github_output, outputs)
        print(f"Published {len(outputs)} outputs to GITHUB_OUTPUT")
        for key, value in outputs.items():
            print(f"  {key}: {value}")


SENSITIVE_KEYS: tuple[str, ...] = (
    "GITOPS_TOKEN",
    "VAULT_ROLE_ID",
    "VAULT_SECRET_ID",
    "DIGITALOCEAN_TOKEN",
    "SPACES_ACCESS_KEY",
    "SPACES_SECRET_KEY",
    "KUBECONFIG_RAW",
    "VAULT_CA_CERTIFICATE",
)


def final_secret_masking() -> None:
    """Perform final pass to ensure sensitive values are masked.

    Examples
    --------
    >>> os.environ["SPACES_ACCESS_KEY"] = "secret"
    >>> final_secret_masking()
    # Emits ::add-mask::secret
    """
    for key in SENSITIVE_KEYS:
        value = os.environ.get(key)
        if value:
            mask_secret(value)


@app.command()
def main(
    cluster_name: str | None = CLUSTER_NAME_PARAM,
    cluster_id: str | None = CLUSTER_ID_PARAM,
    cluster_endpoint: str | None = CLUSTER_ENDPOINT_PARAM,
    gitops_commit_sha: str | None = GITOPS_COMMIT_SHA_PARAM,
    rendered_manifest_count: str | None = RENDERED_MANIFEST_COUNT_PARAM,
    github_output: Path | None = GITHUB_OUTPUT_PARAM,
) -> int:
    """Publish outputs for the nile-valley-infra-k8s action.

    Parameters
    ----------
    cluster_name : str | None
        Cluster name override for ``CLUSTER_NAME``.
    cluster_id : str | None
        Cluster ID override for ``CLUSTER_ID``.
    cluster_endpoint : str | None
        Cluster endpoint override for ``CLUSTER_ENDPOINT``.
    gitops_commit_sha : str | None
        GitOps commit SHA override for ``GITOPS_COMMIT_SHA``.
    rendered_manifest_count : str | None
        Rendered manifest count override for ``RENDERED_MANIFEST_COUNT``.
    github_output : Path | None
        Output file override for ``GITHUB_OUTPUT``.

    Returns
    -------
    int
        Exit code (0 for success).

    Examples
    --------
    Run from the command line::

        $ python scripts/publish_infra_k8s_outputs.py --github-output /tmp/output
    """
    # Resolve GITHUB_OUTPUT path
    github_output_raw = resolve_input(
        github_output,
        InputResolution(env_key="GITHUB_OUTPUT", as_path=True),
    )
    if not github_output_raw:
        msg = "GITHUB_OUTPUT or --github-output must be provided"
        raise SystemExit(msg)
    github_output_path = (
        github_output_raw
        if isinstance(github_output_raw, Path)
        else Path(github_output_raw)
    )

    # Resolve output values from environment
    raw_values = RawOutputValues(
        cluster_name=cluster_name,
        cluster_id=cluster_id,
        cluster_endpoint=cluster_endpoint,
        gitops_commit_sha=gitops_commit_sha,
        rendered_manifest_count=rendered_manifest_count,
    )
    values = resolve_output_values(raw_values)

    # Perform final secret masking
    final_secret_masking()

    # Publish outputs
    publish_outputs(values, github_output_path)

    print("\nOutput publishing complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(app())
