"""Run Git operations for the GitOps manifest workflow.

This module clones a GitOps repository, applies rendered manifests, and
commits changes using token-based authentication. It provides a small
wrapper around git subprocess calls, with validation and error handling
tailored to the nile-valley-infra-k8s action.

Examples
--------
>>> from pathlib import Path
>>> from scripts._gitops_inputs import GitOpsInputs
>>> inputs = GitOpsInputs(
...     gitops_repository="leynos/nile-valley-infra",
...     gitops_branch="main",
...     gitops_token="token",
...     cluster_name="preview-1",
...     render_output_dir=Path("/tmp/rendered"),
...     runner_temp=Path("/tmp"),
...     github_env=Path("/tmp/env"),
...     dry_run=True,
... )
>>> with git_auth_env(inputs.gitops_token, Path("/tmp")) as env:
...     clone_repository(inputs, Path("/tmp/clone"), env)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from scripts._gitops_errors import (
    GitCloneError,
    GitCommandError,
    GitOpsValidationError,
)
from scripts._gitops_inputs import GitOpsInputs
from scripts._infra_k8s import mask_secret

GIT_TIMEOUT_SECONDS = 300


def run_git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    """Run a git command and return stdout.

    Parameters
    ----------
    args : list[str]
        Git arguments (without the ``git`` prefix).
    cwd : Path
        Directory to run the command in.
    env : dict[str, str] | None, optional
        Environment overrides for the command.

    Returns
    -------
    str
        Stdout from the git command.

    Raises
    ------
    GitCommandError
        Raised when the git command fails.
    """
    merged_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=merged_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        msg = (
            f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS}s"
        )
        raise GitCommandError(msg) from exc

    if result.returncode != 0:
        msg = f"git {' '.join(args)} failed: {result.stderr}"
        raise GitCommandError(msg)

    return result.stdout.strip()


@contextmanager
def git_auth_env(token: str, base_dir: Path) -> Iterator[dict[str, str]]:
    """Build environment for Git askpass authentication."""
    base_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        prefix="git-askpass-",
        dir=base_dir,
        encoding="utf-8",
    ) as handle:
        handle.write("#!/bin/sh\nprintf '%s' \"${GITOPS_TOKEN}\"\n")
        askpass_path = Path(handle.name)
    askpass_path.chmod(0o700)
    env = {
        **os.environ,
        "GIT_ASKPASS": str(askpass_path),
        "GIT_TERMINAL_PROMPT": "0",
        "GITOPS_TOKEN": token,
    }
    try:
        yield env
    finally:
        askpass_path.unlink(missing_ok=True)


def clone_repository(
    inputs: GitOpsInputs,
    clone_dir: Path,
    auth_env: dict[str, str],
) -> None:
    """Clone the GitOps repository.

    Parameters
    ----------
    inputs : GitOpsInputs
        Normalized GitOps inputs.
    clone_dir : Path
        Directory for the clone.
    auth_env : dict[str, str]
        Environment containing Git authentication configuration.

    Raises
    ------
    GitCloneError
        Raised when the clone fails.
    """
    mask_secret(inputs.gitops_token)
    repo_url = f"https://x-access-token@github.com/{inputs.gitops_repository}.git"
    masked_repo_url = f"https://x-access-token:***@github.com/{inputs.gitops_repository}.git"

    print(f"Cloning {inputs.gitops_repository}@{inputs.gitops_branch}...")

    # Clone with depth 1 for efficiency
    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                inputs.gitops_branch,
                repo_url,
                str(clone_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=auth_env,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        msg = (
            "git clone timed out after "
            f"{GIT_TIMEOUT_SECONDS}s for {masked_repo_url}"
        )
        raise GitCloneError(msg) from exc
    if result.returncode != 0:
        stderr = result.stderr.replace(inputs.gitops_token, "***")
        msg = f"git clone failed for {masked_repo_url}: {stderr}".strip()
        raise GitCloneError(msg)


def sync_manifests(
    inputs: GitOpsInputs,
    clone_dir: Path,
) -> int:
    """Sync rendered manifests to the GitOps repository.

    Parameters
    ----------
    inputs : GitOpsInputs
        Normalized GitOps inputs.
    clone_dir : Path
        Path to the cloned repository.

    Returns
    -------
    int
        Number of files synced.
    """
    cluster_root = clone_dir / "clusters"
    cluster_dir = cluster_root / inputs.cluster_name
    _reset_cluster_dir(cluster_root, cluster_dir)

    count = 0

    # Copy all rendered manifests to the cluster directory
    if inputs.render_output_dir.exists():
        for src_file in inputs.render_output_dir.rglob("*"):
            if src_file.is_file():
                rel_path = src_file.relative_to(inputs.render_output_dir)
                dest_file = cluster_dir / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)
                count += 1

    return count


def _reset_cluster_dir(cluster_root: Path, cluster_dir: Path) -> None:
    """Ensure the cluster directory is empty and safe to reuse."""
    cluster_root_resolved = cluster_root.resolve()
    clone_dir_resolved = cluster_root.parent.resolve()
    cluster_dir_resolved = cluster_dir.resolve()

    if cluster_root.is_symlink():
        msg = f"Refusing to reset symlinked cluster root {cluster_root}"
        raise GitOpsValidationError(msg)
    if not cluster_root_resolved.is_relative_to(clone_dir_resolved):
        msg = f"Refusing to reset cluster root outside {clone_dir_resolved}"
        raise GitOpsValidationError(msg)
    if not cluster_dir_resolved.is_relative_to(cluster_root_resolved):
        msg = f"Refusing to reset cluster dir outside {cluster_root_resolved}"
        raise GitOpsValidationError(msg)

    if cluster_dir.exists():
        shutil.rmtree(cluster_dir)
    cluster_dir.mkdir(parents=True, exist_ok=True)


def commit_and_push(
    inputs: GitOpsInputs,
    clone_dir: Path,
    auth_env: dict[str, str],
) -> str | None:
    """Commit and push changes to the GitOps repository.

    Parameters
    ----------
    inputs : GitOpsInputs
        Normalized GitOps inputs.
    clone_dir : Path
        Path to the cloned repository.
    auth_env : dict[str, str]
        Environment containing Git authentication configuration.

    Returns
    -------
    str | None
        Commit SHA if changes were pushed, otherwise ``None``.
    """
    # Configure git user for the commit
    run_git(["config", "user.name", "nile-valley-infra-k8s-action"], clone_dir)
    run_git(["config", "user.email", "actions@nile-valley.dev"], clone_dir)

    # Stage all changes
    run_git(["add", "-A"], clone_dir)

    # Check for changes
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=clone_dir,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        msg = (
            "git diff --cached timed out after "
            f"{GIT_TIMEOUT_SECONDS}s"
        )
        raise GitCommandError(msg) from exc

    if result.returncode == 0:
        print("No changes to commit")
        return None

    # Commit changes
    commit_message = f"Update manifests for cluster {inputs.cluster_name}"
    run_git(["commit", "-m", commit_message], clone_dir)

    # Get commit SHA
    commit_sha = run_git(["rev-parse", "HEAD"], clone_dir)

    if inputs.dry_run:
        print(f"Dry run mode - would push commit {commit_sha}")
        return commit_sha

    # Push changes
    print(f"Pushing commit {commit_sha}...")
    run_git(["push", "origin", inputs.gitops_branch], clone_dir, env=auth_env)

    return commit_sha
