#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["plumbum"]
# ///

"""Vault appliance bootstrap helper."""

from __future__ import annotations

import os
import sys
from collections import abc as cabc
from dataclasses import dataclass
from pathlib import Path

from cyclopts import App, Parameter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._input_resolution import InputResolution, resolve_input
from scripts._vault_bootstrap import (
    VaultBootstrapConfig,
    VaultBootstrapError,
    bootstrap,
)

app = App(help="Bootstrap the Vault appliance via environment-derived inputs.")


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    """Vault connection and infrastructure configuration."""

    vault_addr: str | None
    droplet_tag: str | None
    state_file: Path | None
    ca_certificate: Path | None


@dataclass(frozen=True, slots=True)
class SSHConfig:
    """SSH configuration for Vault appliance access."""

    ssh_user: str | None
    ssh_identity: Path | None


@dataclass(frozen=True, slots=True)
class AppRoleConfig:
    """AppRole and KV store configuration."""

    kv_mount_path: str | None
    approle_name: str | None
    approle_policy_name: str | None
    approle_policy_path: Path | None
    approle_policy_content: str | None
    token_ttl: str | None
    token_max_ttl: str | None
    secret_id_ttl: str | None
    rotate_secret_id: bool | str | None


@dataclass(frozen=True, slots=True)
class VaultInitConfig:
    """Vault initialisation configuration."""

    key_shares: int | None
    key_threshold: int | None


@dataclass(frozen=True, slots=True)
class EnvContext:
    """Environment resolution context."""

    env: cabc.Mapping[str, str]

    @classmethod
    def from_os_environ(cls) -> EnvContext:
        """Create context from os.environ."""

        return cls(env=os.environ)


@dataclass(frozen=True, slots=True)
class BootstrapInputs:
    """Grouped bootstrap configuration inputs."""

    connection: ConnectionConfig
    ssh: SSHConfig
    approle: AppRoleConfig
    vault_init: VaultInitConfig


@dataclass(frozen=True, slots=True)
class ShamirConfig:
    """Resolved Shamir configuration."""

    key_shares: int
    key_threshold: int


@dataclass(frozen=True, slots=True)
class TTLConfig:
    """Resolved TTL and rotation configuration."""

    token_ttl: str
    token_max_ttl: str
    secret_id_ttl: str
    rotate_secret_id: bool


@dataclass(frozen=True, slots=True)
class ResolvedConnectionConfig:
    """Resolved Vault connection and infrastructure configuration."""

    vault_addr: str
    droplet_tag: str
    state_file: Path
    ca_certificate: Path | None


@dataclass(frozen=True, slots=True)
class ResolvedSSHConfig:
    """Resolved SSH configuration."""

    ssh_user: str
    ssh_identity: Path | None


@dataclass(frozen=True, slots=True)
class ResolvedAppRoleConfig:
    """Resolved AppRole configuration."""

    kv_mount_path: str
    approle_name: str
    approle_policy_name: str
    approle_policy_path: Path | None


_KEY_THRESHOLD_ERROR = "--key-threshold must be ≤ --key-shares"


def _ensure_policy_path(
    approle_policy_path: Path | None,
    approle_policy_content: str | None,
    state_file: Path,
) -> Path | None:
    """Persist inline policy content alongside the state file when provided."""

    if approle_policy_path is not None:
        return approle_policy_path
    if not approle_policy_content:
        return None
    destination = state_file.parent / "approle-policy.hcl"
    destination.write_text(approle_policy_content, encoding="utf-8")
    destination.chmod(0o600)
    return destination


def _to_bool(*, value: str | bool | None) -> bool:
    """Coerce a bool, string or None to a bool using common truthy spellings."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_core_config(
    *,
    connection: ConnectionConfig,
    context: EnvContext,
) -> ResolvedConnectionConfig:
    """Resolve the state file, Vault address, droplet tag and optional CA path."""
    resolved_state_file = resolve_input(
        connection.state_file,
        InputResolution(env_key="STATE_FILE", required=True, as_path=True),
        env=context.env,
    )
    assert isinstance(resolved_state_file, Path), "STATE_FILE must resolve to a Path"
    resolved_vault_addr = resolve_input(
        connection.vault_addr,
        InputResolution(env_key="VAULT_ADDRESS", required=True),
        env=context.env,
    )
    resolved_droplet_tag = resolve_input(
        connection.droplet_tag,
        InputResolution(env_key="DROPLET_TAG", required=True),
        env=context.env,
    )
    assert resolved_vault_addr, "VAULT_ADDRESS must resolve"
    assert resolved_droplet_tag, "DROPLET_TAG must resolve"
    resolved_ca_certificate = resolve_input(
        connection.ca_certificate,
        InputResolution(env_key="CA_CERT_PATH", as_path=True),
        env=context.env,
    )
    return ResolvedConnectionConfig(
        vault_addr=str(resolved_vault_addr),
        droplet_tag=str(resolved_droplet_tag),
        state_file=resolved_state_file,
        ca_certificate=resolved_ca_certificate if isinstance(resolved_ca_certificate, Path) else None,
    )


def _resolve_ssh_config(
    *,
    ssh: SSHConfig,
    context: EnvContext,
) -> ResolvedSSHConfig:
    """Resolve the SSH user (default "root") and optional identity file."""
    resolved_ssh_user = resolve_input(
        ssh.ssh_user,
        InputResolution(env_key="SSH_USER", default="root"),
        env=context.env,
    )
    resolved_ssh_identity = resolve_input(
        ssh.ssh_identity,
        InputResolution(env_key="SSH_IDENTITY", as_path=True),
        env=context.env,
    )
    return ResolvedSSHConfig(
        ssh_user=str(resolved_ssh_user),
        ssh_identity=resolved_ssh_identity if isinstance(resolved_ssh_identity, Path) else None,
    )


def _resolve_approle_config(
    *,
    approle: AppRoleConfig,
    state_file: Path,
    context: EnvContext,
) -> ResolvedAppRoleConfig:
    """Resolve AppRole and KV settings, saving inline policy content to a file."""
    resolved_kv_mount_path = resolve_input(
        approle.kv_mount_path,
        InputResolution(env_key="KV_MOUNT_PATH", default="secret"),
        env=context.env,
    )
    resolved_approle_name = resolve_input(
        approle.approle_name,
        InputResolution(env_key="APPROLE_NAME", default="doks-deployer"),
        env=context.env,
    )
    resolved_approle_policy_name = resolve_input(
        approle.approle_policy_name,
        InputResolution(env_key="APPROLE_POLICY_NAME", default="doks-deployer"),
        env=context.env,
    )
    resolved_policy_content = resolve_input(
        approle.approle_policy_content,
        InputResolution(env_key="APPROLE_POLICY", default=None),
        env=context.env,
    )
    resolved_approle_policy_path = resolve_input(
        approle.approle_policy_path,
        InputResolution(env_key="APPROLE_POLICY_PATH", as_path=True),
        env=context.env,
    )
    policy_path = _ensure_policy_path(
        resolved_approle_policy_path if isinstance(resolved_approle_policy_path, Path) else None,
        str(resolved_policy_content) if resolved_policy_content is not None else None,
        state_file,
    )

    return ResolvedAppRoleConfig(
        kv_mount_path=str(resolved_kv_mount_path),
        approle_name=str(resolved_approle_name),
        approle_policy_name=str(resolved_approle_policy_name),
        approle_policy_path=policy_path,
    )


def _resolve_shamir_config(
    *,
    vault_init: VaultInitConfig,
    context: EnvContext,
) -> ShamirConfig:
    """Resolve Shamir settings as integers and reject threshold above shares."""
    raw_key_shares = resolve_input(
        vault_init.key_shares,
        InputResolution(env_key="KEY_SHARES", default="5"),
        env=context.env,
    )
    try:
        resolved_key_shares = int(raw_key_shares)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        msg = f"KEY_SHARES must be an integer, got: {raw_key_shares!r}"
        raise SystemExit(msg) from exc

    raw_key_threshold = resolve_input(
        vault_init.key_threshold,
        InputResolution(env_key="KEY_THRESHOLD", default="3"),
        env=context.env,
    )
    try:
        resolved_key_threshold = int(raw_key_threshold)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        msg = f"KEY_THRESHOLD must be an integer, got: {raw_key_threshold!r}"
        raise SystemExit(msg) from exc

    if resolved_key_threshold > resolved_key_shares:
        raise SystemExit(_KEY_THRESHOLD_ERROR)
    return ShamirConfig(key_shares=resolved_key_shares, key_threshold=resolved_key_threshold)


def _resolve_ttl_config(
    *,
    approle: AppRoleConfig,
    context: EnvContext,
) -> TTLConfig:
    """Resolve token, secret ID TTL and secret rotation settings."""
    resolved_token_ttl = resolve_input(
        approle.token_ttl,
        InputResolution(env_key="TOKEN_TTL", default="1h"),
        env=context.env,
    )
    resolved_token_max_ttl = resolve_input(
        approle.token_max_ttl,
        InputResolution(env_key="TOKEN_MAX_TTL", default="4h"),
        env=context.env,
    )
    resolved_secret_id_ttl = resolve_input(
        approle.secret_id_ttl,
        InputResolution(env_key="SECRET_ID_TTL", default="4h"),
        env=context.env,
    )
    resolved_rotate_secret = _to_bool(
        value=resolve_input(
            approle.rotate_secret_id,
            InputResolution(env_key="ROTATE_SECRET_ID", default="false"),
            env=context.env,
        )
    )
    return TTLConfig(
        token_ttl=str(resolved_token_ttl),
        token_max_ttl=str(resolved_token_max_ttl),
        secret_id_ttl=str(resolved_secret_id_ttl),
        rotate_secret_id=resolved_rotate_secret,
    )


def build_config(
    *,
    inputs: BootstrapInputs,
    context: EnvContext | None = None,
) -> VaultBootstrapConfig:
    """Build a bootstrap configuration from CLI parameters and environment."""

    context = context or EnvContext.from_os_environ()
    core = _resolve_core_config(
        connection=inputs.connection,
        context=context,
    )
    ssh_cfg = _resolve_ssh_config(
        ssh=inputs.ssh,
        context=context,
    )
    approle_cfg = _resolve_approle_config(
        approle=inputs.approle,
        state_file=core.state_file,
        context=context,
    )
    shamir_cfg = _resolve_shamir_config(
        vault_init=inputs.vault_init,
        context=context,
    )
    ttl_cfg = _resolve_ttl_config(approle=inputs.approle, context=context)

    return VaultBootstrapConfig(
        vault_addr=core.vault_addr,
        droplet_tag=core.droplet_tag,
        state_file=core.state_file,
        ssh_user=ssh_cfg.ssh_user,
        ssh_identity=ssh_cfg.ssh_identity,
        kv_mount_path=approle_cfg.kv_mount_path,
        approle_name=approle_cfg.approle_name,
        approle_policy_name=approle_cfg.approle_policy_name,
        approle_policy_path=approle_cfg.approle_policy_path,
        key_shares=shamir_cfg.key_shares,
        key_threshold=shamir_cfg.key_threshold,
        token_ttl=ttl_cfg.token_ttl,
        token_max_ttl=ttl_cfg.token_max_ttl,
        secret_id_ttl=ttl_cfg.secret_id_ttl,
        rotate_secret_id=ttl_cfg.rotate_secret_id,
        ca_certificate=core.ca_certificate,
    )


@app.command()
def main(
    vault_addr: str | None = Parameter(),
    droplet_tag: str | None = Parameter(),
    state_file: Path | None = Parameter(),
    ssh_user: str | None = Parameter(),
    ssh_identity: Path | None = Parameter(),
    ca_certificate: Path | None = Parameter(),
    kv_mount_path: str | None = Parameter(),
    approle_name: str | None = Parameter(),
    approle_policy_name: str | None = Parameter(),
    approle_policy_path: Path | None = Parameter(),
    approle_policy_content: str | None = Parameter(),
    key_shares: int | None = Parameter(),
    key_threshold: int | None = Parameter(),
    token_ttl: str | None = Parameter(),
    token_max_ttl: str | None = Parameter(),
    secret_id_ttl: str | None = Parameter(),
    rotate_secret_id: bool | str | None = Parameter(),
) -> int:
    """Entry point for command-line execution."""

    inputs = BootstrapInputs(
        connection=ConnectionConfig(
            vault_addr=vault_addr,
            droplet_tag=droplet_tag,
            state_file=state_file,
            ca_certificate=ca_certificate,
        ),
        ssh=SSHConfig(
            ssh_user=ssh_user,
            ssh_identity=ssh_identity,
        ),
        approle=AppRoleConfig(
            kv_mount_path=kv_mount_path,
            approle_name=approle_name,
            approle_policy_name=approle_policy_name,
            approle_policy_path=approle_policy_path,
            approle_policy_content=approle_policy_content,
            token_ttl=token_ttl,
            token_max_ttl=token_max_ttl,
            secret_id_ttl=secret_id_ttl,
            rotate_secret_id=rotate_secret_id,
        ),
        vault_init=VaultInitConfig(
            key_shares=key_shares,
            key_threshold=key_threshold,
        ),
    )

    config = build_config(
        inputs=inputs,
    )
    try:
        state = bootstrap(config)
    except VaultBootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Vault appliance bootstrap complete.")
    if state.approle_role_id and state.approle_secret_id:
        print("AppRole credentials available in the state file for downstream use.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(app())
