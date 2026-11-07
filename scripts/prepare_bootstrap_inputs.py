#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///
"""Prepare Vault bootstrap inputs for the composite GitHub Action.

The script replaces the inline shell+Python snippets in the composite action
with a small, testable helper. It:

- resolves default paths for the state file, CA certificate, and SSH identity;
- materialises any provided bootstrap payloads (raw or base64-encoded);
- writes GitHub Action environment exports to ``$GITHUB_ENV``; and
- masks sensitive SSH keys in logs.
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from cyclopts import App, Parameter
from scripts._input_resolution import InputResolution, resolve_input

type Mask = Callable[[str], None]

app = App(help="Materialise Vault bootstrap inputs and export env values.")


@dataclass(frozen=True, slots=True)
class GitHubActionContext:
    """Contextual paths and helpers provided by the GitHub Action runner."""

    runner_temp: Path
    github_env: Path
    github_output: Path | None = None
    mask: Mask = print


@dataclass(frozen=True, slots=True)
class BootstrapPayloads:
    """Optional payloads supplied to seed bootstrap artefacts."""

    bootstrap_state: str | None = None
    ca_certificate: str | None = None
    ssh_key: str | None = None


@dataclass(frozen=True, slots=True)
class VaultEnvironmentConfig:
    """Configuration describing the Vault environment under bootstrap."""

    environment: str
    droplet_tag: str | None = None
    state_path: Path | None = None
    vault_address: str | None = None


@dataclass(frozen=True, slots=True)
class RawInputs:
    """Raw CLI and environment inputs before resolution."""

    environment: str | None
    runner_temp: Path | None
    droplet_tag: str | None
    state_path: Path | None
    bootstrap_state: str | None
    ca_certificate: str | None
    ssh_key: str | None
    github_env: Path | None


@dataclass(frozen=True, slots=True)
class ResolvedInputs:
    """All CLI and environment inputs resolved to their final values."""

    environment: str
    runner_temp: Path
    github_env: Path
    droplet_tag: str | None
    state_path: Path | None
    bootstrap_state: str | None
    ca_certificate: str | None
    ssh_key: str | None


@dataclass(frozen=True, slots=True)
class PreparedPaths:
    """Resolved paths produced by the preparation step."""

    droplet_tag: str
    state_file: Path
    ca_certificate_path: Path | None
    ssh_identity_path: Path | None


def _narrow_path(value: str | Path | None) -> Path | None:
    """Return value when it is already a Path; otherwise None."""

    return value if isinstance(value, Path) else None


def _narrow_str(value: str | Path | None) -> str | None:
    """Return value when it is already a string; otherwise None."""

    return value if isinstance(value, str) else None


def _decode_payload(payload: str) -> str:
    """Return payload as text, decoding base64 if it is valid."""

    candidate = payload.strip()
    if not candidate:
        return ""

    try:
        decoded = base64.b64decode(candidate, validate=True)
    except (base64.binascii.Error, ValueError):
        return candidate

    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return candidate


def _write_payload_file(payload: str, destination: Path) -> None:
    """Write decoded payload to destination, validating JSON when applicable."""

    decoded = _decode_payload(payload)
    if not decoded:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.suffix == ".json":
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:  # pragma: no cover - safety net
            msg = f"Invalid JSON supplied for {destination.name}: {exc}"
            raise SystemExit(msg) from exc
        decoded = json.dumps(parsed, indent=2)

    destination.write_text(decoded, encoding="utf-8")
    destination.chmod(0o600)


def _append_env(env_file: Path, lines: list[str]) -> None:
    """Append lines to env_file, creating its parent directory if needed."""
    env_file.parent.mkdir(parents=True, exist_ok=True)
    with env_file.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line}\n")


def _handle_state_file(
    state_path: Path | None,
    environment: str,
    runner_temp: Path,
    bootstrap_state: str | None,
) -> Path:
    """Resolve and materialise the bootstrap state file when provided."""

    state_file = state_path or runner_temp / "vault-bootstrap" / environment / "state.json"
    if not state_file.exists() and bootstrap_state:
        _write_payload_file(bootstrap_state, state_file)
    return state_file


def _handle_ca_certificate(
    ca_certificate: str | None,
    state_file: Path,
) -> Path | None:
    """Materialise the CA certificate payload when present."""

    if not ca_certificate:
        return None
    ca_cert_path = state_file.parent / "vault-ca.pem"
    _write_payload_file(ca_certificate, ca_cert_path)
    return ca_cert_path


def _handle_ssh_identity(
    ssh_key: str | None,
    state_file: Path,
    mask: Mask,
) -> Path | None:
    """Materialise the SSH identity file and mask its contents."""

    if not ssh_key:
        return None
    ssh_identity = state_file.parent / "vault-ssh-key"
    ssh_identity.parent.mkdir(parents=True, exist_ok=True)
    ssh_identity.write_text(f"{ssh_key}\n", encoding="utf-8")
    ssh_identity.chmod(0o600)
    mask(f"::add-mask::{ssh_key}")
    return ssh_identity


def prepare_bootstrap_inputs(
    *,
    vault_config: VaultEnvironmentConfig,
    payloads: BootstrapPayloads,
    github_context: GitHubActionContext,
) -> PreparedPaths:
    """Materialise input payloads and export paths to GITHUB_ENV.

    Parameters
    ----------
    vault_config : VaultEnvironmentConfig
        Resolved identifiers and destination paths for the target environment.
    payloads : BootstrapPayloads
        Optional payloads provided to seed state, CA certificate, and SSH
        identity files.
    github_context : GitHubActionContext
        GitHub Action runner context including temp directories and masking
        helper.

    Returns
    -------
    PreparedPaths
        Resolved paths for the droplet tag, state file, CA certificate, and SSH
        identity.
    """

    resolved_droplet_tag = vault_config.droplet_tag or f"vault-{vault_config.environment}"
    state_file = _handle_state_file(
        vault_config.state_path,
        vault_config.environment,
        github_context.runner_temp,
        payloads.bootstrap_state,
    )
    ca_cert_path = _handle_ca_certificate(payloads.ca_certificate, state_file)
    ssh_identity = _handle_ssh_identity(
        payloads.ssh_key,
        state_file,
        github_context.mask,
    )

    env_lines = [
        f"DROPLET_TAG={resolved_droplet_tag}",
        f"STATE_FILE={state_file}",
    ]
    if ca_cert_path:
        env_lines.append(f"CA_CERT_PATH={ca_cert_path}")
    if ssh_identity:
        env_lines.append(f"SSH_IDENTITY={ssh_identity}")

    _append_env(github_context.github_env, env_lines)

    return PreparedPaths(
        droplet_tag=resolved_droplet_tag,
        state_file=state_file,
        ca_certificate_path=ca_cert_path,
        ssh_identity_path=ssh_identity,
    )

def _resolve_all_inputs(
    raw: RawInputs,
) -> ResolvedInputs:
    """Resolve CLI and env inputs to their canonical types."""

    resolved_environment = resolve_input(
        raw.environment,
        InputResolution(env_key="INPUT_ENVIRONMENT", required=True),
    )
    resolved_runner_temp = resolve_input(
        raw.runner_temp,
        InputResolution(
            env_key="RUNNER_TEMP",
            default=Path(tempfile.gettempdir()),
            as_path=True,
        ),
    )
    resolved_github_env = resolve_input(
        raw.github_env,
        InputResolution(
            env_key="GITHUB_ENV",
            default=Path(tempfile.gettempdir()) / "github-env-undefined",
            as_path=True,
        ),
    )
    resolved_droplet_tag = resolve_input(
        raw.droplet_tag, InputResolution(env_key="INPUT_DROPLET_TAG")
    )
    resolved_state_path = resolve_input(
        raw.state_path,
        InputResolution(env_key="INPUT_STATE_PATH", as_path=True),
    )
    resolved_bootstrap_state = resolve_input(
        raw.bootstrap_state,
        InputResolution(env_key="INPUT_BOOTSTRAP_STATE"),
    )
    resolved_ca_certificate = resolve_input(
        raw.ca_certificate,
        InputResolution(env_key="INPUT_CA_CERTIFICATE"),
    )
    resolved_ssh_key = resolve_input(
        raw.ssh_key, InputResolution(env_key="INPUT_SSH_KEY")
    )

    return ResolvedInputs(
        environment=str(resolved_environment),
        runner_temp=_narrow_path(resolved_runner_temp) or Path(tempfile.gettempdir()),
        github_env=_narrow_path(resolved_github_env)
        or Path(tempfile.gettempdir()) / "github-env-undefined",
        droplet_tag=_narrow_str(resolved_droplet_tag),
        state_path=_narrow_path(resolved_state_path),
        bootstrap_state=_narrow_str(resolved_bootstrap_state),
        ca_certificate=_narrow_str(resolved_ca_certificate),
        ssh_key=_narrow_str(resolved_ssh_key),
    )


def _build_parameter_objects(
    inputs: ResolvedInputs,
) -> tuple[VaultEnvironmentConfig, BootstrapPayloads, GitHubActionContext]:
    """Construct parameter objects for the bootstrap helper."""

    vault_config = VaultEnvironmentConfig(
        environment=inputs.environment,
        droplet_tag=inputs.droplet_tag,
        state_path=inputs.state_path,
        vault_address=None,
    )
    payloads = BootstrapPayloads(
        bootstrap_state=inputs.bootstrap_state,
        ca_certificate=inputs.ca_certificate,
        ssh_key=inputs.ssh_key,
    )
    github_context = GitHubActionContext(
        runner_temp=inputs.runner_temp,
        github_env=inputs.github_env,
        github_output=None,
        mask=print,
    )
    return vault_config, payloads, github_context


@app.command()
def main(
    environment: str | None = Parameter(),
    runner_temp: Path | None = Parameter(),
    droplet_tag: str | None = Parameter(),
    state_path: Path | None = Parameter(),
    bootstrap_state: str | None = Parameter(),
    ca_certificate: str | None = Parameter(),
    ssh_key: str | None = Parameter(),
    github_env: Path | None = Parameter(),
) -> None:
    """CLI entrypoint used by the composite action.

    Parameters
    ----------
    environment : str | None, optional
        Vault environment name; falls back to ``INPUT_ENVIRONMENT``.
    runner_temp : Path | None, optional
        Runner temporary directory; falls back to ``RUNNER_TEMP``.
    droplet_tag : str | None, optional
        DigitalOcean droplet tag; falls back to ``INPUT_DROPLET_TAG``.
    state_path : Path | None, optional
        Custom state file path; falls back to ``INPUT_STATE_PATH``.
    bootstrap_state : str | None, optional
        Bootstrap state payload; falls back to ``INPUT_BOOTSTRAP_STATE``.
    ca_certificate : str | None, optional
        CA certificate payload; falls back to ``INPUT_CA_CERTIFICATE``.
    ssh_key : str | None, optional
        SSH private key payload; falls back to ``INPUT_SSH_KEY``.
    github_env : Path | None, optional
        GitHub environment file path; falls back to ``GITHUB_ENV``.
    """

    raw = RawInputs(
        environment,
        runner_temp,
        droplet_tag,
        state_path,
        bootstrap_state,
        ca_certificate,
        ssh_key,
        github_env,
    )
    inputs = _resolve_all_inputs(raw)
    vault_config, payloads, github_context = _build_parameter_objects(inputs)

    prepare_bootstrap_inputs(
        vault_config=vault_config,
        payloads=payloads,
        github_context=github_context,
    )


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    app()
