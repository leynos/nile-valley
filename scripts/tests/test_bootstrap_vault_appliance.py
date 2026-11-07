"""Tests for the Vault appliance bootstrap helper."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from cmd_mox import CmdMox, Response
from plumbum import local

from scripts._vault_bootstrap import bootstrap
from scripts._vault_state import (
    VaultBootstrapConfig,
    VaultBootstrapError,
    VaultBootstrapState,
)
from scripts.bootstrap_vault_appliance import (
    AppRoleConfig,
    BootstrapInputs,
    ConnectionConfig,
    EnvContext,
    SSHConfig,
    VaultInitConfig,
    build_config,
)


def _make_config(tmp_path: Path, **overrides: object) -> VaultBootstrapConfig:
    """Build a VaultBootstrapConfig in tmp_path, applying keyword overrides."""
    state_file = tmp_path / "state.json"
    defaults: dict[str, object] = {
        "vault_addr": "https://vault.example",
        "droplet_tag": "vault-dev",
        "state_file": state_file,
    }
    defaults.update(overrides)
    return VaultBootstrapConfig(**defaults)


def _sync_plumbum_path() -> None:
    """Align ``plumbum.local`` with the real environment variables."""

    local.env["PATH"] = os.environ["PATH"]

    desired_cmd_vars = {key for key in os.environ if key.startswith("CMOX_")}
    active_cmd_vars = {
        key for key in local.env.keys() if key.startswith("CMOX_")
    }

    for key in desired_cmd_vars:
        local.env[key] = os.environ[key]

    for key in active_cmd_vars - desired_cmd_vars:
        local.env.pop(key, None)


def _stub_doctl(mox: CmdMox, ip: str) -> None:
    """Stub doctl to list one droplet tagged vault-dev with the given IP."""
    mox.stub("doctl").with_args(
        "compute",
        "droplet",
        "list",
        "--tag-name",
        "vault-dev",
        "--output",
        "json",
    ).returns(
        stdout=json.dumps(
            [
                {
                    "networks": {
                        "v4": [
                            {
                                "type": "public",
                                "ip_address": ip,
                            }
                        ]
                    }
                }
            ]
        )
    ).times(1)


def _stub_ssh(mox: CmdMox, ip: str, *, user: str = "root") -> None:
    """Stub ssh to report the vault service as active on the given host."""
    mox.stub("ssh").with_args(
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        f"{user}@{ip}",
        "systemctl",
        "is-active",
        "vault",
    ).returns(stdout="active\n").times(1)


def _build_configured_vault_handler(
    config: VaultBootstrapConfig,
) -> Callable:
    """Return a Vault handler for an already configured cluster.

    Example:
        >>> from pathlib import Path
        >>> config = VaultBootstrapConfig("https://vault", "tag", Path("state.json"))
        >>> handler = _build_configured_vault_handler(config)
        >>> invocation = type("Invocation", (), {"args": ["status", "-format=json"]})
        >>> handler(invocation).stdout
        '{"initialized": true, "sealed": false}'
    """

    command_responses: dict[tuple[str, ...], Response] = {
        ("status", "-format=json"): Response(
            stdout=json.dumps({"initialized": True, "sealed": False})
        ),
        ("secrets", "list", "-format=json"): Response(
            stdout=json.dumps(
                {"secret/": {"type": "kv", "options": {"version": "2"}}}
            )
        ),
        ("auth", "list", "-format=json"): Response(
            stdout=json.dumps({"approle/": {"type": "approle"}})
        ),
        (
            "read",
            "-field=role_id",
            f"auth/approle/role/{config.approle_name}/role-id",
        ): Response(stdout="role-id\n"),
    }

    def handler(invocation) -> Response:
        """Answer vault calls for a configured cluster and reject secret rotation."""
        args = tuple(invocation.args)
        if args in command_responses:
            return command_responses[args]
        if args[:2] == ("policy", "write"):
            return Response(stdout="")
        if args[:2] == (
            "write",
            f"auth/approle/role/{config.approle_name}",
        ):
            return Response(stdout="")
        if args[:3] == ("write", "-force", "-format=json"):
            raise AssertionError("secret-id rotation should be skipped")
        raise AssertionError(f"Unexpected vault invocation: {args}")

    return handler


def test_bootstrap_initializes_vault(tmp_path: Path) -> None:
    """Initial bootstrap initializes, unseals, and provisions the AppRole."""

    policy = tmp_path / "policy.hcl"
    policy_content = "path \"secret/data/*\" { capabilities = [\"read\"] }\n"
    policy.write_text(policy_content, encoding="utf-8")

    config = _make_config(tmp_path, approle_policy_path=policy)

    vault_state = {
        "status_calls": 0,
        "unseal_calls": 0,
    }

    def vault_handler(invocation) -> Response:
        """Serve Vault CLI calls for a fresh cluster that must be initialised."""
        args = invocation.args
        env = invocation.env
        assert env["VAULT_ADDR"] == config.vault_addr
        if args == ["status", "-format=json"]:
            vault_state["status_calls"] += 1
            match vault_state["status_calls"]:
                case 1:
                    payload = {"initialized": False, "sealed": True}
                case 2:
                    payload = {"initialized": True, "sealed": True}
                case _:
                    payload = {"initialized": True, "sealed": False}
            return Response(stdout=json.dumps(payload))
        if args[:3] == ["operator", "init", "-key-shares"]:
            return Response(
                stdout=json.dumps(
                    {
                        "unseal_keys_b64": ["key1", "key2", "key3"],
                        "root_token": "root-token",
                    }
                )
            )
        if args[:3] == ["operator", "unseal", "-format=json"]:
            vault_state["unseal_calls"] += 1
            sealed = vault_state["unseal_calls"] < 3
            return Response(stdout=json.dumps({"sealed": sealed}))
        if args[:3] == ["secrets", "list", "-format=json"]:
            return Response(stdout=json.dumps({}))
        if args[:2] == ["secrets", "enable"]:
            return Response(stdout="")
        if args[:3] == ["auth", "list", "-format=json"]:
            return Response(stdout=json.dumps({}))
        if args[:2] == ["auth", "enable"]:
            return Response(stdout="")
        if args[:2] == ["policy", "write"]:
            assert invocation.stdin == policy_content
            return Response(stdout="")
        if args[0:2] == ["write", f"auth/approle/role/{config.approle_name}"]:
            return Response(stdout="")
        if args[:2] == ["read", "-field=role_id"]:
            return Response(stdout="role-id\n")
        if args[:3] == ["write", "-force", "-format=json"]:
            return Response(stdout=json.dumps({"data": {"secret_id": "secret-id"}}))
        raise AssertionError(f"Unexpected vault invocation: {args}")

    with CmdMox() as mox:
        _stub_doctl(mox, "203.0.113.10")
        _stub_ssh(mox, "203.0.113.10")
        mox.stub("vault").runs(vault_handler)
        mox.replay()
        _sync_plumbum_path()
        state = bootstrap(config)

    _sync_plumbum_path()

    assert state.root_token == "root-token"
    assert state.approle_role_id == "role-id"
    assert state.approle_secret_id == "secret-id"

    saved = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert saved["root_token"] == "root-token"
    assert saved["approle_secret_id"] == "secret-id"


def test_bootstrap_skips_when_already_configured(tmp_path: Path) -> None:
    """A subsequent run verifies mounts and retains the existing secret ID."""

    state = VaultBootstrapState(
        unseal_keys=["key1", "key2", "key3"],
        root_token="root-token",
        approle_role_id="role-id",
        approle_secret_id="existing-secret",
    )
    config = _make_config(tmp_path)
    config.state_file.write_text(json.dumps(state.to_mapping()), encoding="utf-8")

    with CmdMox() as mox:
        _stub_doctl(mox, "203.0.113.10")
        _stub_ssh(mox, "203.0.113.10")
        mox.stub("vault").runs(_build_configured_vault_handler(config))
        mox.replay()
        _sync_plumbum_path()
        result_state = bootstrap(config)

    _sync_plumbum_path()

    assert result_state.approle_secret_id == "existing-secret"


def _build_rotation_test_handler(
    config: VaultBootstrapConfig, should_rotate: bool
) -> tuple[Callable, Callable[[], int]]:
    """Build a vault command handler for testing secret rotation behaviour.

    Returns a tuple of (handler_function, get_rotation_count_function).

    Example:
        >>> from pathlib import Path
        >>> config = VaultBootstrapConfig("https://vault", "tag", Path("state.json"))
        >>> handler, get_count = _build_rotation_test_handler(config, True)
        >>> invocation = type(
        ...     "Invocation",
        ...     (),
        ...     {"args": ("status", "-format=json"), "env": {"VAULT_ADDR": config.vault_addr}},
        ... )
        >>> handler(invocation).stdout
        '{"initialized": true, "sealed": false}'
        >>> get_count()
        0
    """

    rotation_invocations = 0

    command_responses: dict[tuple[str, ...], Response] = {
        ("status", "-format=json"): Response(
            stdout=json.dumps({"initialized": True, "sealed": False})
        ),
        ("secrets", "list", "-format=json"): Response(
            stdout=json.dumps(
                {"secret/": {"type": "kv", "options": {"version": "2"}}}
            )
        ),
        ("auth", "list", "-format=json"): Response(
            stdout=json.dumps({"approle/": {"type": "approle"}})
        ),
        (
            "read",
            "-field=role_id",
            f"auth/approle/role/{config.approle_name}/role-id",
        ): Response(stdout="role-id\n"),
    }

    def get_rotation_count() -> int:
        """Return how many secret-ID rotation writes the handler has seen."""
        return rotation_invocations

    def handler(invocation) -> Response:
        """Answer vault calls, counting secret-ID rotation writes."""
        nonlocal rotation_invocations
        args = tuple(invocation.args)
        if args in command_responses:
            return command_responses[args]
        if args[:2] == ("policy", "write"):
            return Response(stdout="")
        if args[:2] == (
            "write",
            f"auth/approle/role/{config.approle_name}",
        ):
            return Response(stdout="")
        if args[:3] == ("write", "-force", "-format=json"):
            rotation_invocations += 1
            if not should_rotate:
                raise AssertionError("secret-id rotation should be skipped")
            payload = json.dumps({"data": {"secret_id": "rotated-secret"}})
            return Response(stdout=payload)
        raise AssertionError(f"Unexpected vault invocation: {args}")

    return handler, get_rotation_count


@pytest.mark.parametrize(
    ("rotate_secret_id", "expected_secret", "should_rotate"),
    [
        pytest.param(False, "existing-secret", False, id="retain"),
        pytest.param(True, "rotated-secret", True, id="rotate"),
    ],
)
def test_bootstrap_respects_secret_rotation(
    tmp_path: Path,
    rotate_secret_id: bool,
    expected_secret: str,
    should_rotate: bool,
) -> None:
    """Bootstrap honours the secret rotation flag when configuring Vault."""

    state = VaultBootstrapState(
        unseal_keys=["key1", "key2", "key3"],
        root_token="root-token",
        approle_role_id="role-id",
        approle_secret_id="existing-secret",
    )
    config = _make_config(tmp_path, rotate_secret_id=rotate_secret_id)
    config.state_file.write_text(json.dumps(state.to_mapping()), encoding="utf-8")

    vault_handler, get_rotation_count = _build_rotation_test_handler(
        config, should_rotate
    )

    with CmdMox() as mox:
        _stub_doctl(mox, "203.0.113.10")
        _stub_ssh(mox, "203.0.113.10")
        mox.stub("vault").runs(vault_handler)
        mox.replay()
        _sync_plumbum_path()
        result_state = bootstrap(config)

    _sync_plumbum_path()

    assert get_rotation_count() == int(should_rotate)
    assert result_state.approle_secret_id == expected_secret


def test_bootstrap_errors_when_unseal_keys_missing(tmp_path: Path) -> None:
    """Fail fast when Vault is sealed but the state file lacks key shares."""

    config = _make_config(tmp_path)
    config.state_file.write_text(json.dumps({"root_token": "root-token"}), encoding="utf-8")

    def vault_handler(invocation) -> Response:
        """Report a sealed, initialised Vault so bootstrap needs unseal keys."""
        args = invocation.args
        if args == ["status", "-format=json"]:
            return Response(stdout=json.dumps({"initialized": True, "sealed": True}))
        raise AssertionError(f"Unexpected vault invocation: {args}")

    with CmdMox() as mox:
        _stub_doctl(mox, "203.0.113.10")
        _stub_ssh(mox, "203.0.113.10")
        mox.stub("vault").runs(vault_handler)
        mox.replay()
        _sync_plumbum_path()
        with pytest.raises(VaultBootstrapError) as exc:
            bootstrap(config)

    _sync_plumbum_path()

    assert "no unseal keys" in str(exc.value)


def test_parse_args_validates_threshold_not_exceeding_shares(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI parsing rejects a key threshold larger than the number of shares."""

    state_file = tmp_path / "state.json"

    with pytest.raises(SystemExit):
        inputs = BootstrapInputs(
            connection=ConnectionConfig(
                vault_addr="https://vault.example",
                droplet_tag="vault-dev",
                state_file=state_file,
                ca_certificate=None,
            ),
            ssh=SSHConfig(ssh_user=None, ssh_identity=None),
            approle=AppRoleConfig(
                kv_mount_path=None,
                approle_name=None,
                approle_policy_name=None,
                approle_policy_path=None,
                approle_policy_content=None,
                token_ttl=None,
                token_max_ttl=None,
                secret_id_ttl=None,
                rotate_secret_id=None,
            ),
            vault_init=VaultInitConfig(key_shares=3, key_threshold=4),
        )
        build_config(
            inputs=inputs,
            context=EnvContext(env={}),
        )
