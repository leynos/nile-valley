"""Unit tests for the publish_bootstrap_outputs helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.publish_bootstrap_outputs import (
    BootstrapOutputs,
    GitHubActionContext,
    VaultEnvironmentConfig,
    publish_bootstrap_outputs,
)


def test_masks_secrets_and_writes_outputs(tmp_path: Path) -> None:
    """Check that secrets are masked and the outputs are written to the file."""
    state_file = tmp_path / "state.json"
    state_file.write_text(
        """
        {
          "approle_role_id": "role-123",
          "approle_secret_id": "secret-abc",
          "root_token": "root-xyz",
          "unseal_keys": ["key1", "key2"]
        }
        """,
        encoding="utf-8",
    )
    output_file = tmp_path / "out"
    ca_path = tmp_path / "vault-ca.pem"
    ca_path.write_text("ca", encoding="utf-8")
    masks: list[str] = []

    result = publish_bootstrap_outputs(
        vault_config=VaultEnvironmentConfig(
            environment="dev",
            droplet_tag=None,
            state_path=state_file,
            vault_address="https://vault",
        ),
        github_context=GitHubActionContext(
            runner_temp=tmp_path,
            github_env=tmp_path / "env",
            github_output=output_file,
            mask=masks.append,
        ),
    )

    assert isinstance(result, BootstrapOutputs)
    assert result.approle_role_id == "role-123"
    assert result.approle_secret_id == "secret-abc"

    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert "vault-address=https://vault" in lines
    assert f"state-file={state_file}" in lines
    assert "approle-role-id=role-123" in lines
    assert "approle-secret-id=secret-abc" in lines
    assert f"ca-certificate-path={ca_path}" in lines

    assert masks == [
        "::add-mask::secret-abc",
        "::add-mask::root-xyz",
        "::add-mask::key1",
        "::add-mask::key2",
    ]


def test_missing_state_file_errors(tmp_path: Path) -> None:
    """Check that a missing state file raises FileNotFoundError."""
    output_file = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        publish_bootstrap_outputs(
            vault_config=VaultEnvironmentConfig(
                environment="dev",
                droplet_tag=None,
                state_path=tmp_path / "missing.json",
                vault_address="https://vault",
            ),
            github_context=GitHubActionContext(
                runner_temp=tmp_path,
                github_env=tmp_path / "env",
                github_output=output_file,
                mask=lambda _secret: None,
            ),
        )
