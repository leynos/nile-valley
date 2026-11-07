"""Unit tests for publish_infra_k8s_outputs."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from scripts.publish_infra_k8s_outputs import (
    OutputValues,
    RawOutputValues,
    final_secret_masking,
    publish_outputs,
    resolve_output_values,
)


def test_resolve_output_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that cluster output values are resolved from the environment."""
    monkeypatch.setenv("CLUSTER_NAME", "preview")
    monkeypatch.setenv("CLUSTER_ID", "abc")
    monkeypatch.setenv("CLUSTER_ENDPOINT", "https://kube")

    values = resolve_output_values(RawOutputValues())
    assert values.cluster_name == "preview", "Cluster name should resolve"
    assert values.cluster_id == "abc", "Cluster ID should resolve"
    assert values.cluster_endpoint == "https://kube", "Endpoint should resolve"


def test_publish_outputs_writes_file(tmp_path: Path) -> None:
    """Check that publish_outputs writes each value to the output file."""
    output_file = tmp_path / "out"
    values = OutputValues(
        cluster_name="preview",
        cluster_id="abc",
        cluster_endpoint=None,
        gitops_commit_sha="sha",
        rendered_manifest_count="3",
    )

    publish_outputs(values, output_file)

    content = output_file.read_text(encoding="utf-8")
    assert "cluster_name=preview" in content, "Cluster name should be published"
    assert "gitops_commit_sha=sha" in content, "Commit SHA should be published"
    assert "rendered_manifest_count=3" in content, "Render count should be published"


def test_final_secret_masking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that the GitOps token from the environment is masked."""
    token = _dummy_token()
    monkeypatch.setenv("GITOPS_TOKEN", token)
    masked: list[str] = []
    monkeypatch.setattr("scripts.publish_infra_k8s_outputs.mask_secret", masked.append)

    final_secret_masking()

    assert token in masked, "Token should be masked"


def _dummy_token() -> str:
    """Return a random token-like string for use as a test secret."""
    return f"token-{secrets.token_hex(8)}"
