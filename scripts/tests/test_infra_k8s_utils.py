"""Unit tests for shared nile-valley-infra-k8s helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts._infra_k8s import (
    TofuResult,
    TofuCommandError,
    append_github_env,
    append_github_output,
    parse_bool,
    parse_node_pools,
    run_tofu,
    tofu_output,
    validate_cluster_name,
    write_manifests,
    write_tfvars,
)


def test_parse_bool_defaults() -> None:
    assert parse_bool(None) is True, "Default should be True when value is None"
    assert (
        parse_bool(None, default=False) is False
    ), "Default override should be honored"


def test_parse_bool_truthy_and_falsey() -> None:
    assert parse_bool("true") is True, "true should parse to True"
    assert parse_bool("YES") is True, "YES should parse to True"
    assert parse_bool("1") is True, "1 should parse to True"
    assert parse_bool("false") is False, "false should parse to False"
    assert parse_bool("0") is False, "0 should parse to False"


def test_parse_node_pools_valid() -> None:
    pools = parse_node_pools('[{"name": "default"}]')
    assert isinstance(pools, list), "Expected list of node pools"
    assert pools[0]["name"] == "default", "Expected default pool name"


def test_parse_node_pools_rejects_non_list() -> None:
    with pytest.raises(TypeError, match="node_pools must be a JSON array"):
        parse_node_pools('{"name": "default"}')


def test_append_github_env_supports_multiline(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    append_github_env(env_file, {"KUBECONFIG_RAW": "line1\nline2"})
    content = env_file.read_text(encoding="utf-8")
    assert content.startswith("KUBECONFIG_RAW<<"), "Expected heredoc header"
    assert "line1\nline2" in content, "Expected multiline content"


def test_append_github_env_single_line(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    append_github_env(env_file, {"CLUSTER_NAME": "preview-1"})
    assert (
        env_file.read_text(encoding="utf-8") == "CLUSTER_NAME=preview-1\n"
    ), "Single-line env should be written directly"


def test_append_github_output_supports_multiline(tmp_path: Path) -> None:
    output_file = tmp_path / "out"
    append_github_output(output_file, {"kubeconfig": "line1\nline2"})
    content = output_file.read_text(encoding="utf-8")
    assert content.startswith("kubeconfig<<"), "Expected heredoc header"
    assert "line1\nline2" in content, "Expected multiline content"


def test_write_tfvars_and_manifests(tmp_path: Path) -> None:
    tfvars_path = tmp_path / "vars" / "vars.tfvars.json"
    write_tfvars(tfvars_path, {"cluster_name": "preview"})
    data = json.loads(tfvars_path.read_text(encoding="utf-8"))
    assert data == {"cluster_name": "preview"}, "tfvars should round trip"

    count = write_manifests(
        tmp_path / "out",
        {"platform/traefik.yaml": "apiVersion: v1"},
    )
    assert count == 1, "Expected one manifest to be written"
    manifest_path = tmp_path / "out" / "platform" / "traefik.yaml"
    assert (
        manifest_path.read_text(encoding="utf-8") == "apiVersion: v1"
    ), "Manifest content should match"


def test_validate_cluster_name_normalizes() -> None:
    assert (
        validate_cluster_name(" Preview-1 ") == "preview-1"
    ), "Cluster name should be normalized"


@pytest.mark.parametrize("value", ["", "Invalid_Name", "-bad", "bad-"])
def test_validate_cluster_name_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError, match="cluster_name"):
        validate_cluster_name(value)


class _StubResult:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_tofu_invokes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> _StubResult:
        cmd = args[0]
        assert isinstance(cmd, list), "Expected command argument list"
        assert all(isinstance(part, str) for part in cmd), "Command parts must be strings"
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return _StubResult()

    monkeypatch.setattr("scripts._infra_k8s_tofu.subprocess.run", fake_run)

    result = run_tofu(["plan", "-input=false"], tmp_path)
    assert isinstance(result, TofuResult), "Expected TofuResult return"
    assert captured["cmd"][0] == "tofu", "Expected tofu command prefix"
    assert captured["cwd"] == tmp_path, "Expected cwd to be passed"


def test_run_tofu_rejects_invalid_args(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid control character"):
        run_tofu(["plan\n"], tmp_path)


def test_tofu_output_raises_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> TofuResult:
        return TofuResult(success=False, stdout="", stderr="boom", return_code=1)

    monkeypatch.setattr("scripts._infra_k8s_tofu.run_tofu", fake_run)

    with pytest.raises(TofuCommandError, match="tofu output failed"):
        tofu_output(tmp_path)


def test_write_manifests_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Refusing to write manifest"):
        write_manifests(tmp_path, {"../escape.yaml": "apiVersion: v1"})
