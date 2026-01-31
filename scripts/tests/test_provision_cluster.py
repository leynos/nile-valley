"""Unit tests for provision_cluster."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts._infra_k8s import TofuResult
from scripts._provision_cluster_flow import export_cluster_outputs, provision_cluster
from scripts._provision_cluster_inputs import (
    ProvisionInputs,
    RawProvisionInputs,
    build_backend_config,
    build_tfvars,
    resolve_provision_inputs,
)


def _make_inputs(tmp_path: Path, **overrides: object) -> ProvisionInputs:
    defaults: dict[str, object] = {
        "cluster_name": "preview-1",
        "environment": "preview",
        "region": "nyc1",
        "kubernetes_version": "1.33.1-do.3",
        "node_pools": json.dumps(
            [
                {
                    "name": "default",
                    "size": "s-2vcpu-2gb",
                    "node_count": 2,
                    "auto_scale": False,
                    "min_nodes": 2,
                    "max_nodes": 2,
                }
            ]
        ),
        "spaces_bucket": "nile-valley-tofu-state",
        "spaces_region": "nyc3",
        "spaces_access_key": "access",
        "spaces_secret_key": "secret",
        "runner_temp": tmp_path,
        "github_env": tmp_path / "env",
        "dry_run": True,
    }
    defaults.update(overrides)
    return ProvisionInputs(**defaults)


def test_build_backend_config(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    backend = build_backend_config(inputs)
    assert (
        backend.endpoint == "https://nyc3.digitaloceanspaces.com"
    ), "Expected Spaces endpoint to match region"
    assert (
        backend.state_key == "clusters/preview-1/terraform.tfstate"
    ), "Expected state key to include cluster name"


def test_build_tfvars_includes_node_pools(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    tfvars = build_tfvars(inputs)
    assert (
        tfvars["cluster_name"] == "preview-1"
    ), "Expected cluster_name to be written to tfvars"
    assert isinstance(
        tfvars["node_pools"], list
    ), "Expected node_pools to be a list in tfvars"


def test_resolve_provision_inputs_cli_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLUSTER_NAME", "env-name")
    monkeypatch.setenv("ENVIRONMENT", "preview")
    monkeypatch.setenv("REGION", "nyc1")
    monkeypatch.setenv("SPACES_ACCESS_KEY", "access")
    monkeypatch.setenv("SPACES_SECRET_KEY", "secret")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))

    inputs = resolve_provision_inputs(RawProvisionInputs(cluster_name="cli-name"))
    assert inputs.cluster_name == "cli-name", "CLI override should win"


def test_provision_cluster_dry_run_skips_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path, dry_run=True)
    backend = build_backend_config(inputs)
    tfvars = build_tfvars(inputs)
    calls: list[str] = []

    def fake_init(*_args: object, **_kwargs: object) -> TofuResult:
        calls.append("init")
        return TofuResult(success=True, stdout="", stderr="", return_code=0)

    def fake_plan(*_args: object, **_kwargs: object) -> TofuResult:
        calls.append("plan")
        return TofuResult(success=True, stdout="", stderr="", return_code=0)

    def fake_apply(*_args: object, **_kwargs: object) -> TofuResult:
        calls.append("apply")
        return TofuResult(success=True, stdout="", stderr="", return_code=0)

    monkeypatch.setattr("scripts._provision_cluster_flow.tofu_init", fake_init)
    monkeypatch.setattr("scripts._provision_cluster_flow.tofu_plan", fake_plan)
    monkeypatch.setattr("scripts._provision_cluster_flow.tofu_apply", fake_apply)

    success, outputs = provision_cluster(inputs, backend, tfvars)
    assert success is True, "Expected dry-run provision to succeed"
    assert outputs == {}, "Expected no outputs in dry-run mode"
    assert "apply" not in calls, "Dry-run should skip apply"


def test_provision_cluster_apply_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path, dry_run=False)
    backend = build_backend_config(inputs)
    tfvars = build_tfvars(inputs)

    monkeypatch.setattr(
        "scripts._provision_cluster_flow.tofu_init",
        lambda *_args, **_kwargs: TofuResult(
            success=True,
            stdout="",
            stderr="",
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        "scripts._provision_cluster_flow.tofu_plan",
        lambda *_args, **_kwargs: TofuResult(
            success=True,
            stdout="",
            stderr="",
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        "scripts._provision_cluster_flow.tofu_apply",
        lambda *_args, **_kwargs: TofuResult(
            success=True,
            stdout="",
            stderr="",
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        "scripts._provision_cluster_flow.tofu_output",
        lambda *_args, **_kwargs: {"cluster_id": {"value": "abc"}},
    )

    success, outputs = provision_cluster(inputs, backend, tfvars)
    assert success is True, "Expected provision to succeed"
    assert (
        outputs["cluster_id"]["value"] == "abc"
    ), "Expected cluster_id output to be populated"


def test_export_cluster_outputs_writes_kubeconfig(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    env_file = inputs.github_env
    masked: list[str] = []

    monkeypatch.setattr("scripts._provision_cluster_flow.mask_secret", masked.append)

    export_cluster_outputs(
        inputs,
        {
            "cluster_id": "abc",
            "endpoint": "https://kube",
            "kubeconfig": "line1\nline2",
        },
    )

    content = env_file.read_text(encoding="utf-8")
    assert "CLUSTER_ID=abc" in content, "Expected cluster ID to be exported"
    assert "KUBECONFIG_RAW<<" in content, "Expected kubeconfig to export multiline"
    assert masked, "Expected secrets to be masked"
