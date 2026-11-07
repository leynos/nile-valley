"""Unit tests for the prepare_bootstrap_inputs helper."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from scripts.prepare_bootstrap_inputs import (
    BootstrapPayloads,
    GitHubActionContext,
    PreparedPaths,
    VaultEnvironmentConfig,
    prepare_bootstrap_inputs,
)


def test_writes_state_and_exports_env(tmp_path: Path) -> None:
    """Bootstrap state is saved privately, and env values are exported and masked."""
    env_file = tmp_path / "env"
    runner_temp = tmp_path / "rt"
    state_payload = base64.b64encode(b'{"hello":"world"}').decode("utf-8")
    ca_payload = "-----BEGIN CERT-----\nabc\n-----END CERT-----"

    masks: list[str] = []
    paths = prepare_bootstrap_inputs(
        vault_config=VaultEnvironmentConfig(
            environment="dev",
            droplet_tag=None,
            state_path=None,
            vault_address=None,
        ),
        payloads=BootstrapPayloads(
            bootstrap_state=state_payload,
            ca_certificate=ca_payload,
            ssh_key="ssh-secret",
        ),
        github_context=GitHubActionContext(
            runner_temp=runner_temp,
            github_env=env_file,
            mask=masks.append,
            github_output=None,
        ),
    )

    expected_state = runner_temp / "vault-bootstrap" / "dev" / "state.json"
    assert paths.state_file == expected_state

    state_data = json.loads(expected_state.read_text(encoding="utf-8"))
    assert state_data == {"hello": "world"}
    assert paths.state_file.stat().st_mode & 0o777 == 0o600

    assert paths.droplet_tag == "vault-dev"
    assert paths.ca_certificate_path is not None
    assert paths.ca_certificate_path.read_text(encoding="utf-8") == ca_payload
    assert paths.ssh_identity_path is not None
    assert paths.ssh_identity_path.read_text(encoding="utf-8").strip() == "ssh-secret"

    env_lines = env_file.read_text(encoding="utf-8").splitlines()
    assert f"DROPLET_TAG={paths.droplet_tag}" in env_lines
    assert f"STATE_FILE={paths.state_file}" in env_lines
    assert f"CA_CERT_PATH={paths.ca_certificate_path}" in env_lines
    assert f"SSH_IDENTITY={paths.ssh_identity_path}" in env_lines

    assert masks == ["::add-mask::ssh-secret"]


def test_respects_explicit_paths_and_skips_blank_payloads(tmp_path: Path) -> None:
    """An explicit state path is used, and blank payloads write no files."""
    env_file = tmp_path / "env"
    state_path = tmp_path / "state.json"

    paths = prepare_bootstrap_inputs(
        vault_config=VaultEnvironmentConfig(
            environment="prod",
            droplet_tag="vault-prod",
            state_path=state_path,
            vault_address=None,
        ),
        payloads=BootstrapPayloads(
            bootstrap_state=None,
            ca_certificate="",
            ssh_key="",
        ),
        github_context=GitHubActionContext(
            runner_temp=tmp_path,
            github_env=env_file,
            github_output=None,
            mask=lambda _secret: None,
        ),
    )

    assert paths.state_file == state_path
    assert not paths.state_file.exists()
    assert paths.ca_certificate_path is None
    assert paths.ssh_identity_path is None

    env_lines = env_file.read_text(encoding="utf-8").splitlines()
    assert env_lines == [
        "DROPLET_TAG=vault-prod",
        f"STATE_FILE={state_path}",
    ]


def test_invalid_json_raises(tmp_path: Path) -> None:
    """Invalid JSON in the bootstrap state exits with an error."""
    env_file = tmp_path / "env"

    with pytest.raises(SystemExit, match=r"Invalid JSON supplied"):
        prepare_bootstrap_inputs(
            vault_config=VaultEnvironmentConfig(
                environment="dev",
                droplet_tag=None,
                state_path=None,
                vault_address=None,
            ),
            payloads=BootstrapPayloads(
                bootstrap_state="not-json",
                ca_certificate=None,
                ssh_key=None,
            ),
            github_context=GitHubActionContext(
                runner_temp=tmp_path,
                github_env=env_file,
                github_output=None,
                mask=lambda _secret: None,
            ),
        )
