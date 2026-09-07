"""Tests for the OpenTofu validate-and-plan gate.

The gate replaced Make recipes that ran ``tofu validate`` and ``tofu plan``
from one shell line and then captured ``$?``, so a validation failure was
discarded. These tests pin the ordering, the first-failure behaviour and the
opt-in skip that the recipes provided.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import GateError
from scripts._tofu_modules import MODULES, UnknownModuleError
from scripts.tests.gate_test_support import (
    activate,
    commands_run,
    empty_search_path,
)
from scripts.tests.tofu_gate_test_support import (
    TRAEFIK_ENVIRONMENT,
    stub_tofu,
    tofu_calls,
)
from scripts.tofu_example_gate import main

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)


@pytest.fixture(name="traefik_environment")
def traefik_environment_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the Traefik gate with every required variable present."""
    for name, value in TRAEFIK_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def test_gate_is_skipped_when_the_kubeconfig_is_unset(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without a cluster the gate reports a skip and runs nothing."""
    monkeypatch.delenv("TRAEFIK_KUBECONFIG_PATH", raising=False)
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    main(module="traefik")

    assert "Skipping traefik" in capsys.readouterr().out
    assert commands_run(cmd_mox) == []


def test_incomplete_environment_is_reported_before_tofu_runs(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every missing companion variable is named in one failure."""
    monkeypatch.setenv("TRAEFIK_KUBECONFIG_PATH", "/tmp/kubeconfig")
    monkeypatch.delenv("TRAEFIK_ACME_EMAIL", raising=False)
    monkeypatch.delenv("TRAEFIK_CLOUDFLARE_SECRET_NAME", raising=False)
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(module="traefik")

    message = str(excinfo.value)
    assert "TRAEFIK_ACME_EMAIL" in message
    assert "TRAEFIK_CLOUDFLARE_SECRET_NAME" in message
    assert commands_run(cmd_mox) == []


@pytest.mark.usefixtures("traefik_environment")
def test_validate_runs_before_plan(cmd_mox: CmdMox) -> None:
    """Both steps run, in the order the recipe used."""
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    main(module="traefik")

    assert tofu_calls(cmd_mox) == ["validate", "plan"]


@pytest.mark.usefixtures("traefik_environment")
def test_failing_validate_stops_the_gate(cmd_mox: CmdMox) -> None:
    """A validation failure is named and the plan never runs.

    This is the defect the script replaces: the shell recipe went on to plan
    and reported the plan's status to Make.
    """
    stub_tofu(cmd_mox, {"validate": 1})
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(module="traefik")

    assert "tofu validate" in str(excinfo.value)
    assert tofu_calls(cmd_mox) == ["validate"]


@pytest.mark.usefixtures("traefik_environment")
def test_failing_plan_is_reported(cmd_mox: CmdMox) -> None:
    """A plan failure fails the gate after a clean validation."""
    stub_tofu(cmd_mox, {"plan": 1})
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(module="traefik")

    assert "tofu plan" in str(excinfo.value)
    assert tofu_calls(cmd_mox) == ["validate", "plan"]


@pytest.mark.usefixtures("traefik_environment")
def test_pending_changes_are_not_a_failure(cmd_mox: CmdMox) -> None:
    """``-detailed-exitcode`` returns 2 for drift, which the gate accepts."""
    stub_tofu(cmd_mox, {"plan": 2})
    activate(cmd_mox)

    main(module="traefik")

    assert tofu_calls(cmd_mox) == ["validate", "plan"]


@pytest.mark.usefixtures("traefik_environment")
def test_environment_values_reach_tofu(cmd_mox: CmdMox) -> None:
    """Each module variable is passed as a ``-var`` assignment."""
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    main(module="traefik")

    validate_args = list(cmd_mox.journal[0].args)
    assert validate_args[0] == "-chdir=infra/modules/traefik/examples/basic"
    assert "kubeconfig_path=/tmp/kubeconfig" in validate_args
    assert "acme_email=ops@example.test" in validate_args
    assert "cloudflare_api_token_secret_name=cloudflare-token" in validate_args


def test_flux_plan_uses_documented_defaults(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset Flux repository variables fall back to the sample repository."""
    monkeypatch.setenv("FLUX_KUBECONFIG_PATH", "/tmp/kubeconfig")
    for name in (
        "FLUX_GIT_REPOSITORY_URL",
        "FLUX_GIT_REPOSITORY_PATH",
        "FLUX_GIT_REPOSITORY_BRANCH",
    ):
        monkeypatch.delenv(name, raising=False)
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    main(module="fluxcd")

    plan_args = list(cmd_mox.journal[1].args)
    assert "git_repository_branch=main" in plan_args
    assert "git_repository_path=./clusters/my-cluster" in plan_args
    assert any(argument.startswith("git_repository_url=http") for argument in plan_args)
    # Validation takes only the kubeconfig, as the recipe did.
    assert not any(
        argument.startswith("git_repository") for argument in cmd_mox.journal[0].args
    )


def test_unknown_module_is_rejected() -> None:
    """A misspelt module name fails loudly rather than gating nothing."""
    with pytest.raises(UnknownModuleError):
        main(module="not-a-module")


def test_every_registered_module_declares_an_example() -> None:
    """The registry points at examples that exist in the repository."""
    for module in MODULES.values():
        assert module.example_path.is_dir(), module.key


def test_missing_tofu_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent OpenTofu binary is reported before the gate decides to skip."""
    with (
        empty_search_path(monkeypatch, tmp_path / "empty-bin"),
        pytest.raises(GateError) as excinfo,
    ):
        main(module="traefik")

    assert "tofu" in str(excinfo.value)
