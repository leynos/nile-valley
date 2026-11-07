"""Structural tests for the bootstrap-vault-appliance composite action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ACTION_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github/actions/bootstrap-vault-appliance/action.yml"
)


def _load_action() -> dict[str, Any]:
    """Load the bootstrap-vault-appliance action metadata as a mapping."""
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def test_inputs_cover_credentials_and_env() -> None:
    """Check required inputs, and that token and state lack a secret key."""
    action = _load_action()
    inputs = action["inputs"]

    assert inputs["environment"]["required"] is True
    assert inputs["vault_address"]["required"] is True

    digitalocean = inputs["digitalocean_token"]
    assert digitalocean["required"] is True
    # GitHub Actions does not support marking inputs as "secret" in the action
    # metadata. Secrets are still passed via workflow `secrets.*` bindings.
    assert "secret" not in digitalocean, (
        "digitalocean_token must not have a 'secret' key in action metadata"
    )

    bootstrap_state = inputs["bootstrap_state"]
    assert bootstrap_state["required"] is False
    assert "secret" not in bootstrap_state, (
        "bootstrap_state must not have a 'secret' key in action metadata"
    )


def test_bootstrap_step_invokes_helper_with_idempotent_flags() -> None:
    """Assert the bootstrap step runs the helper with the expected env wiring."""
    action = _load_action()
    steps = action["runs"]["steps"]
    bootstrap = next(
        step for step in steps if step["name"] == "Bootstrap Vault appliance"
    )
    run_script = bootstrap["run"]
    env = bootstrap.get("env", {})

    assert run_script.strip() == "uv run scripts/bootstrap_vault_appliance.py"
    expected_env = {
        "VAULT_ADDRESS": "${{ inputs.vault_address }}",
        "DROPLET_TAG": "${{ env.DROPLET_TAG }}",
        "STATE_FILE": "${{ env.STATE_FILE }}",
        "ROTATE_SECRET_ID": "${{ inputs.rotate_secret_id }}",
    }
    for key, value in expected_env.items():
        assert env.get(key) == value


def test_publish_step_emits_expected_outputs() -> None:
    """Assert the action declares and wires the outputs, and the script masks."""
    action = _load_action()
    outputs = action["outputs"]

    expected = {
        "vault-address",
        "ca-certificate-path",
        "state-file",
        "approle-role-id",
        "approle-secret-id",
    }
    assert expected.issubset(outputs.keys())

    publish_step = next(
        step for step in action["runs"]["steps"]
        if step["id"] == "publish"
    )
    publish_run = publish_step["run"]
    assert "uv run scripts/publish_bootstrap_outputs.py" in publish_run
    publish_script = Path(__file__).resolve().parents[2] / "scripts/publish_bootstrap_outputs.py"
    assert "add-mask" in publish_script.read_text(encoding="utf-8")

    expected_wiring = {
        "vault-address": "${{ steps.publish.outputs.vault-address }}",
        "ca-certificate-path": "${{ steps.publish.outputs.ca-certificate-path }}",
        "state-file": "${{ steps.publish.outputs.state-file }}",
        "approle-role-id": "${{ steps.publish.outputs.approle-role-id }}",
        "approle-secret-id": "${{ steps.publish.outputs.approle-secret-id }}",
    }
    for key, value in expected_wiring.items():
        assert outputs[key]["value"] == value
