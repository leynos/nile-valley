"""Structural tests for the nile-valley-infra-k8s composite action."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

ACTION_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github/actions/nile-valley-infra-k8s/action.yml"
)


def _load_action() -> dict[str, object]:
    result = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
    assert isinstance(result, dict)
    return cast(dict[str, object], result)


def _assert_step_invokes_script(
    action: dict[str, object],
    *,
    step_id: str,
    expected_substring: str,
) -> None:
    runs = action.get("runs")
    assert isinstance(runs, dict), "action['runs'] must be a mapping"
    steps = runs.get("steps")
    assert isinstance(steps, list), "action['runs']['steps'] must be a list"
    assert all(isinstance(step, dict) for step in steps), (
        "action['runs']['steps'] must contain step mappings"
    )

    step = next(
        (
            candidate
            for candidate in steps
            if isinstance(candidate, dict) and candidate.get("id") == step_id
        ),
        None,
    )
    assert step is not None, f"Missing {step_id} step"
    run_value = step.get("run", "")
    assert isinstance(run_value, str), f"{step_id} step run must be a string"
    assert expected_substring in run_value, f"{step_id} step should invoke expected script"


def test_required_inputs_are_marked_as_required() -> None:
    """Verify all essential inputs are marked as required."""
    action = _load_action()
    inputs = action["inputs"]
    assert isinstance(inputs, dict)

    required_inputs = [
        "cluster_name",
        "environment",
        "region",
        "domain",
        "acme_email",
        "gitops_repository",
        "gitops_token",
        "digitalocean_token",
        "spaces_access_key",
        "spaces_secret_key",
    ]

    for input_name in required_inputs:
        assert input_name in inputs, f"Missing required input: {input_name}"
        assert inputs[input_name]["required"] is True, (
            f"Input {input_name} should be required"
        )


def test_optional_inputs_have_defaults() -> None:
    """Verify optional inputs have sensible defaults."""
    action = _load_action()
    inputs = action["inputs"]
    assert isinstance(inputs, dict)

    optional_with_defaults = {
        "gitops_branch": "main",
        "cloudflare_api_token_secret_name": "cloudflare-api-token",
        "enable_traefik": "true",
        "enable_cert_manager": "true",
        "enable_external_dns": "true",
        "enable_vault_eso": "true",
        "enable_cnpg": "true",
        "dry_run": "false",
    }

    for input_name, expected_default in optional_with_defaults.items():
        assert input_name in inputs, f"Missing optional input: {input_name}"
        assert inputs[input_name].get("required", False) is False, (
            f"Input {input_name} should not be required"
        )
        assert inputs[input_name].get("default") == expected_default, (
            f"Input {input_name} should default to {expected_default}"
        )


def test_sensitive_inputs_not_marked_as_secret() -> None:
    """Verify sensitive inputs don't have invalid 'secret' key.

    GitHub Actions does not support marking inputs as "secret" in the action
    metadata. Secrets are passed via workflow `secrets.*` bindings.
    """
    action = _load_action()
    inputs = action["inputs"]
    assert isinstance(inputs, dict)

    sensitive_inputs = [
        "gitops_token",
        "vault_role_id",
        "vault_secret_id",
        "digitalocean_token",
        "spaces_access_key",
        "spaces_secret_key",
    ]

    for input_name in sensitive_inputs:
        assert input_name in inputs, f"Missing sensitive input: {input_name}"
        assert "secret" not in inputs[input_name], (
            f"{input_name} must not have a 'secret' key in action metadata"
        )


def test_outputs_are_properly_wired() -> None:
    """Verify outputs are wired to the publish step."""
    action = _load_action()
    outputs = action["outputs"]
    assert isinstance(outputs, dict)

    expected_outputs = {
        "cluster_name": "${{ steps.publish.outputs.cluster_name }}",
        "cluster_id": "${{ steps.publish.outputs.cluster_id }}",
        "cluster_endpoint": "${{ steps.publish.outputs.cluster_endpoint }}",
        "gitops_commit_sha": "${{ steps.publish.outputs.gitops_commit_sha }}",
        "rendered_manifest_count": "${{ steps.publish.outputs.rendered_manifest_count }}",
    }

    for output_name, expected_value in expected_outputs.items():
        assert output_name in outputs, f"Missing output: {output_name}"
        assert outputs[output_name]["value"] == expected_value, (
            f"Output {output_name} should be wired to {expected_value}"
        )


def test_prepare_step_invokes_correct_script() -> None:
    """Verify the prepare step invokes prepare_infra_k8s_inputs.py."""
    action = _load_action()
    runs = action["runs"]
    assert isinstance(runs, dict)
    steps = runs["steps"]
    assert isinstance(steps, list)

    prepare = next(
        (
            step
            for step in steps
            if isinstance(step, dict) and step.get("id") == "prepare"
        ),
        None,
    )
    assert prepare is not None, "Missing prepare step"

    assert "uv run scripts/prepare_infra_k8s_inputs.py" in prepare["run"]

    # Verify essential environment variables are set
    env = prepare.get("env", {})
    assert isinstance(env, dict)
    essential_env_vars = [
        "INPUT_CLUSTER_NAME",
        "INPUT_ENVIRONMENT",
        "INPUT_REGION",
        "INPUT_DOMAIN",
        "INPUT_ACME_EMAIL",
        "INPUT_GITOPS_REPOSITORY",
        "INPUT_GITOPS_TOKEN",
        "INPUT_VAULT_ADDRESS",
        "INPUT_VAULT_ROLE_ID",
        "INPUT_VAULT_SECRET_ID",
        "INPUT_DIGITALOCEAN_TOKEN",
        "INPUT_SPACES_ACCESS_KEY",
        "INPUT_SPACES_SECRET_KEY",
    ]

    for var in essential_env_vars:
        assert var in env, f"Missing environment variable in prepare step: {var}"


def test_provision_step_invokes_correct_script() -> None:
    """Verify the provision step invokes provision_cluster.py."""
    action = _load_action()
    runs = action["runs"]
    assert isinstance(runs, dict)
    steps = runs["steps"]
    assert isinstance(steps, list)

    provision = next(
        (
            step
            for step in steps
            if isinstance(step, dict) and step.get("id") == "provision"
        ),
        None,
    )
    assert provision is not None, "Missing provision step"

    assert "uv run scripts/provision_cluster.py" in provision["run"]

    # Verify DigitalOcean credentials are passed
    env = provision.get("env", {})
    assert isinstance(env, dict)
    assert "DIGITALOCEAN_TOKEN" in env
    assert "SPACES_ACCESS_KEY" in env
    assert "SPACES_SECRET_KEY" in env


def test_render_step_invokes_correct_script() -> None:
    """Verify the render step invokes render_platform_manifests.py."""
    action = _load_action()
    _assert_step_invokes_script(
        action,
        step_id="render",
        expected_substring="uv run scripts/render_platform_manifests.py",
    )


def test_commit_step_is_conditional_on_dry_run() -> None:
    """Verify the commit step is skipped in dry-run mode."""
    action = _load_action()
    runs = action["runs"]
    assert isinstance(runs, dict)
    steps = runs["steps"]
    assert isinstance(steps, list)

    commit = next(
        (
            step
            for step in steps
            if isinstance(step, dict) and step.get("id") == "commit"
        ),
        None,
    )
    assert commit is not None, "Missing commit step"

    assert "uv run scripts/commit_gitops_manifests.py" in commit["run"]
    assert commit.get("if") == (
        '${{ !contains(fromJSON(\'["true","True","TRUE","1","yes","Yes","YES"]\'), inputs.dry_run) }}'
    ), (
        "Commit step should be conditional on dry_run input"
    )


def test_publish_step_invokes_correct_script() -> None:
    """Verify the publish step invokes publish_infra_k8s_outputs.py."""
    action = _load_action()
    _assert_step_invokes_script(
        action,
        step_id="publish",
        expected_substring="uv run scripts/publish_infra_k8s_outputs.py",
    )


def test_uses_composite_action_runner() -> None:
    """Verify the action uses composite runner."""
    action = _load_action()

    runs = action["runs"]
    assert isinstance(runs, dict)

    assert runs["using"] == "composite"


def test_installs_required_tools() -> None:
    """Verify required tools are installed."""
    action = _load_action()
    runs = action["runs"]
    assert isinstance(runs, dict)
    steps = runs["steps"]
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps), (
        "action['runs']['steps'] must contain step mappings"
    )

    step_names = [step.get("name", "") for step in steps]

    assert any("uv" in name.lower() for name in step_names), (
        "Action should install uv"
    )
    assert any("opentofu" in name.lower() or "tofu" in name.lower() for name in step_names), (
        "Action should install OpenTofu"
    )
    assert any("doctl" in name.lower() for name in step_names), (
        "Action should install doctl"
    )


def test_scripts_use_secret_masking() -> None:
    """Verify helper scripts use secret masking."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"

    scripts = {
        "prepare_infra_k8s_inputs.py": (
            "prepare_infra_k8s_inputs.py should use mask_secret"
        ),
        "provision_cluster.py": "provision_cluster.py should use mask_secret",
        "commit_gitops_manifests.py": "commit_gitops_manifests.py should use mask_secret",
        "publish_infra_k8s_outputs.py": (
            "publish_infra_k8s_outputs.py should use mask_secret"
        ),
    }

    for script_name, error_message in scripts.items():
        content = (scripts_dir / script_name).read_text(encoding="utf-8")
        assert "mask_secret" in content, error_message
