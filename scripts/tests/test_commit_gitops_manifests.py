"""Unit tests for commit_gitops_manifests."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from scripts.commit_gitops_manifests import (
    GitOpsInputs,
    RawGitOpsInputs,
    clone_repository,
    commit_and_push,
    git_auth_env,
    resolve_gitops_inputs,
    sync_manifests,
)


def _make_inputs(tmp_path: Path, **overrides: object) -> GitOpsInputs:
    token = _dummy_token()
    defaults: dict[str, object] = {
        "gitops_repository": "leynos/nile-valley-infra",
        "gitops_branch": "main",
        "gitops_token": token,
        "cluster_name": "preview-1",
        "render_output_dir": tmp_path / "render",
        "runner_temp": tmp_path,
        "github_env": tmp_path / "env",
        "dry_run": False,
    }
    defaults.update(overrides)
    return GitOpsInputs(**defaults)

def _dummy_token() -> str:
    return f"token-{secrets.token_hex(8)}"


def test_resolve_gitops_inputs_cli_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token = _dummy_token()
    monkeypatch.setenv("GITOPS_REPOSITORY", "leynos/env")
    monkeypatch.setenv("GITOPS_TOKEN", token)
    monkeypatch.setenv("CLUSTER_NAME", "env")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "env"))

    inputs = resolve_gitops_inputs(RawGitOpsInputs(gitops_repository="cli"))
    assert inputs.gitops_repository == "cli", "CLI override should win for repository"


def test_clone_repository_uses_askpass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token = _dummy_token()
    inputs = _make_inputs(tmp_path, gitops_token=token)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    captured: dict[str, object] = {}

    class _Result:
        def __init__(self) -> None:
            self.returncode = 0
            self.stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> _Result:  # type: ignore[override]
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return _Result()

    monkeypatch.setattr("scripts._gitops_repo.subprocess.run", fake_run)

    with git_auth_env(inputs.gitops_token, tmp_path) as auth_env:
        clone_repository(inputs, clone_dir, auth_env)

        cmd = captured["cmd"]
        assert token not in " ".join(cmd), "Token should not appear in clone command"
        env = captured["env"]
        assert isinstance(env, dict), "Expected auth env to be a dict"
        assert env.get("GITOPS_TOKEN") == token, "Auth env should expose token"
        assert env.get("GIT_ASKPASS"), "Auth env should set GIT_ASKPASS"

        askpass_path = Path(env["GIT_ASKPASS"])
        assert askpass_path.exists(), "Askpass script should exist during use"
        assert token not in askpass_path.read_text(
            encoding="utf-8"
        ), "Askpass script should not embed the token"
    assert not askpass_path.exists(), "Askpass script should be cleaned up"


def test_sync_manifests_copies_files(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.render_output_dir.mkdir(parents=True)
    (inputs.render_output_dir / "platform").mkdir()
    source = inputs.render_output_dir / "platform" / "manifest.yaml"
    source.write_text("apiVersion: v1", encoding="utf-8")

    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    count = sync_manifests(inputs, clone_dir)
    assert count == 1, "Expected one manifest to be synced"
    dest = clone_dir / "clusters" / inputs.cluster_name / "platform" / "manifest.yaml"
    assert (
        dest.read_text(encoding="utf-8") == "apiVersion: v1"
    ), "Synced manifest content mismatch"


def test_sync_manifests_removes_stale_files(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    inputs.render_output_dir.mkdir(parents=True)
    (inputs.render_output_dir / "platform").mkdir()
    (inputs.render_output_dir / "platform" / "manifest.yaml").write_text(
        "apiVersion: v1",
        encoding="utf-8",
    )

    clone_dir = tmp_path / "clone"
    cluster_dir = clone_dir / "clusters" / inputs.cluster_name / "old"
    cluster_dir.mkdir(parents=True)
    stale_manifest = cluster_dir / "stale.yaml"
    stale_manifest.write_text("stale", encoding="utf-8")

    sync_manifests(inputs, clone_dir)

    assert not stale_manifest.exists(), "Stale manifests should be removed"


def test_commit_and_push_no_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    monkeypatch.setattr("scripts._gitops_repo.run_git", lambda *_args, **_kwargs: "")

    class _Result:
        def __init__(self) -> None:
            self.returncode = 0

    monkeypatch.setattr("scripts._gitops_repo.subprocess.run", lambda *_args, **_kwargs: _Result())

    with git_auth_env(inputs.gitops_token, tmp_path) as auth_env:
        assert (
            commit_and_push(inputs, clone_dir, auth_env) is None
        ), "No changes should yield None commit SHA"


def test_commit_and_push_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path, dry_run=True)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    calls: list[list[str]] = []

    def fake_run_git(
        args: list[str], _cwd: Path, _env: dict[str, str] | None = None
    ) -> str:
        calls.append(args)
        if args[:2] == ["rev-parse", "HEAD"]:
            return "abc123"
        return ""

    monkeypatch.setattr("scripts._gitops_repo.run_git", fake_run_git)

    class _Result:
        def __init__(self) -> None:
            self.returncode = 1

    monkeypatch.setattr("scripts._gitops_repo.subprocess.run", lambda *_args, **_kwargs: _Result())

    with git_auth_env(inputs.gitops_token, tmp_path) as auth_env:
        commit_sha = commit_and_push(inputs, clone_dir, auth_env)
    assert commit_sha == "abc123", "Dry-run should return computed commit SHA"
    assert (
        ["push", "origin", inputs.gitops_branch] not in calls
    ), "Dry-run must not push"
