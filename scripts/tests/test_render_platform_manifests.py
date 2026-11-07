"""Unit tests for render_platform_manifests."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from scripts._infra_k8s import TofuResult
from scripts.render_platform_manifests import (
    RawRenderInputs,
    RenderInputs,
    _extract_rendered_manifests,
    build_render_tfvars,
    render_manifests,
    resolve_render_inputs,
)


def test_resolve_render_inputs_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Check that render inputs resolve from environment variables."""
    monkeypatch.setenv("CLUSTER_NAME", "preview")
    monkeypatch.setenv("DOMAIN", "example.test")
    monkeypatch.setenv("ACME_EMAIL", "admin@example.test")
    monkeypatch.setenv("ENABLE_TRAEFIK", "false")
    monkeypatch.setenv("ENABLE_VAULT_ESO", "false")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("RENDER_OUTPUT_DIR", str(tmp_path / "render"))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))

    inputs = resolve_render_inputs(RawRenderInputs())
    assert inputs.cluster_name == "preview", "Cluster name should resolve"
    assert inputs.enable_traefik is False, "Traefik flag should parse to False"


def test_resolve_render_inputs_cli_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a CLI cluster name overrides the environment value."""
    monkeypatch.setenv("CLUSTER_NAME", "env")
    monkeypatch.setenv("DOMAIN", "example.test")
    monkeypatch.setenv("ACME_EMAIL", "admin@example.test")
    monkeypatch.setenv("ENABLE_VAULT_ESO", "false")

    inputs = resolve_render_inputs(RawRenderInputs(cluster_name="cli"))
    assert inputs.cluster_name == "cli", "CLI override should win"


@pytest.fixture
def cloudflare_secret_name() -> str:
    """Return a random Cloudflare secret name for tests."""
    return f"cloudflare-secret-{secrets.token_hex(4)}"


@pytest.fixture
def vault_secret_value() -> str:
    """Return a random Vault secret value for tests."""
    return f"vault-secret-{secrets.token_hex(6)}"


def test_build_render_tfvars_skips_vault_when_disabled(
    tmp_path: Path,
    cloudflare_secret_name: str,
    vault_secret_value: str,
) -> None:
    """Check that build_render_tfvars omits Vault settings when ESO is off."""
    inputs = RenderInputs(
        cluster_name="preview",
        domain="example.test",
        acme_email="admin@example.test",
        cloudflare_api_token_secret_name=cloudflare_secret_name,
        vault_address="https://vault.example",
        vault_role_id="role",
        vault_secret_id=vault_secret_value,
        vault_ca_certificate="cert",
        enable_traefik=True,
        enable_cert_manager=True,
        enable_external_dns=True,
        enable_vault_eso=False,
        enable_cnpg=True,
        runner_temp=tmp_path,
        output_dir=tmp_path / "out",
        github_env=tmp_path / "env",
    )

    tfvars = build_render_tfvars(inputs)
    assert "vault_address" not in tfvars, "Vault settings should be skipped"
    assert tfvars["vault_eso_enabled"] is False, "Vault ESO should remain disabled"


def test_extract_rendered_manifests_handles_wrapped_value() -> None:
    """Check that manifests wrapped under a value key are unwrapped."""
    outputs = {
        "rendered_manifests": {
            "value": {"platform/traefik.yaml": "apiVersion: v1"}
        }
    }
    manifests = _extract_rendered_manifests(outputs)
    assert (
        manifests == {"platform/traefik.yaml": "apiVersion: v1"}
    ), "Wrapped manifests should be unwrapped"


def test_render_manifests_runs_tofu(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cloudflare_secret_name: str,
) -> None:
    """Check render_manifests makes two tofu calls and returns the manifest."""
    inputs = RenderInputs(
        cluster_name="preview",
        domain="example.test",
        acme_email="admin@example.test",
        cloudflare_api_token_secret_name=cloudflare_secret_name,
        vault_address=None,
        vault_role_id=None,
        vault_secret_id=None,
        vault_ca_certificate=None,
        enable_traefik=True,
        enable_cert_manager=True,
        enable_external_dns=True,
        enable_vault_eso=False,
        enable_cnpg=True,
        runner_temp=tmp_path,
        output_dir=tmp_path / "out",
        github_env=tmp_path / "env",
    )
    tfvars = build_render_tfvars(inputs)

    calls: list[list[str]] = []

    def fake_run_tofu(args: list[str], _cwd: Path) -> TofuResult:
        """Record the tofu arguments and report a successful run."""
        calls.append(args)
        return TofuResult(success=True, stdout="", stderr="", return_code=0)

    monkeypatch.setattr("scripts.render_platform_manifests.run_tofu", fake_run_tofu)
    monkeypatch.setattr(
        "scripts.render_platform_manifests.tofu_output",
        lambda *_args, **_kwargs: {
            "rendered_manifests": {"value": {"platform/traefik.yaml": "apiVersion: v1"}}
        },
    )

    manifests = render_manifests(inputs, tfvars)
    assert "platform/traefik.yaml" in manifests, "Manifest path should be present"
    assert len(calls) == 2, "Expected init and apply calls"

