"""Tests for the OpenTofu plan policy gate.

The gate replaced Make recipes that chained an environment check, a plan, a
JSON export and a conftest run in one shell. These tests pin the ordering,
the first-failure behaviour, and the conftest arguments each module needs.
"""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

import pytest
from cmd_mox import Invocation, Response

from scripts._gate_runner import GateError
from scripts._tofu_modules import MODULES
from scripts.tests.gate_test_support import activate, commands_run
from scripts.tests.tofu_gate_test_support import (
    TRAEFIK_ENVIRONMENT,
    module_environment,
    stub_tofu,
    tofu_calls,
)
from scripts.tofu_plan_policy import main

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

PLAN_JSON = json.dumps({"resource_changes": []})


@pytest.fixture(name="traefik_environment")
def traefik_environment_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the Traefik gate with every required variable present."""
    for name, value in TRAEFIK_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def _stub_policy_tools(
    mox: CmdMox,
    tofu_exit_codes: dict[str, int] | None = None,
    conftest_exit_code: int = 0,
) -> None:
    """Register the tofu and conftest doubles the gate drives."""
    stub_tofu(mox, tofu_exit_codes or {}, {"show": PLAN_JSON})
    mox.stub("conftest").returns(exit_code=conftest_exit_code)


def test_gate_is_skipped_when_the_kubeconfig_is_unset(
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without a cluster the policy gate reports a skip and runs nothing."""
    monkeypatch.delenv("TRAEFIK_KUBECONFIG_PATH", raising=False)
    _stub_policy_tools(cmd_mox)
    activate(cmd_mox)

    main(module="traefik")

    output = capsys.readouterr().out
    assert "Skipping traefik plan policy" in output, f"skip not reported: {output}"
    assert commands_run(cmd_mox) == [], "no tool may run when the gate is disabled"


def test_incomplete_environment_is_reported_before_planning(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-configured gate fails rather than planning with empty values."""
    monkeypatch.setenv("TRAEFIK_KUBECONFIG_PATH", "/tmp/kubeconfig")
    monkeypatch.delenv("TRAEFIK_ACME_EMAIL", raising=False)
    monkeypatch.setenv("TRAEFIK_CLOUDFLARE_SECRET_NAME", "cloudflare-token")
    _stub_policy_tools(cmd_mox)
    activate(cmd_mox)

    with pytest.raises(GateError, match="TRAEFIK_ACME_EMAIL"):
        main(module="traefik")

    assert commands_run(cmd_mox) == [], (
        "the environment must be checked before a plan is written"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_plan_export_and_policy_run_in_order(cmd_mox: CmdMox) -> None:
    """The plan is written, exported and only then checked."""
    _stub_policy_tools(cmd_mox)
    activate(cmd_mox)

    main(module="traefik")

    assert commands_run(cmd_mox) == ["tofu", "tofu", "conftest"], (
        "the plan must be written, exported and only then checked"
    )
    assert tofu_calls(cmd_mox) == ["plan", "show"], (
        "the export must read the plan that was just written"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_failing_plan_stops_before_the_export(cmd_mox: CmdMox) -> None:
    """A plan failure is named and no policy verdict is produced."""
    _stub_policy_tools(cmd_mox, {"plan": 1})
    activate(cmd_mox)

    with pytest.raises(GateError, match=r"tofu plan \(traefik\)"):
        main(module="traefik")

    assert commands_run(cmd_mox) == ["tofu"], (
        "no policy verdict may follow a failed plan"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_failing_export_stops_before_conftest(cmd_mox: CmdMox) -> None:
    """A failed export never reaches conftest as an empty document."""
    _stub_policy_tools(cmd_mox, {"show": 1})
    activate(cmd_mox)

    with pytest.raises(GateError, match=r"tofu show \(traefik\)"):
        main(module="traefik")

    assert commands_run(cmd_mox) == ["tofu", "tofu"], (
        "conftest must not read the output of a failed export"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_failing_policy_is_reported(cmd_mox: CmdMox) -> None:
    """A conftest violation fails the gate."""
    _stub_policy_tools(cmd_mox, conftest_exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError, match="conftest"):
        main(module="traefik")

    assert commands_run(cmd_mox) == ["tofu", "tofu", "conftest"], (
        "the plan and export must precede the failing policy check"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_pending_changes_are_not_a_failure(cmd_mox: CmdMox) -> None:
    """A plan with pending changes is still checked against the policy."""
    _stub_policy_tools(cmd_mox, {"plan": 2})
    activate(cmd_mox)

    main(module="traefik")

    assert commands_run(cmd_mox) == ["tofu", "tofu", "conftest"], (
        "a plan with pending changes must still be checked"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_conftest_receives_the_modules_policy_settings(cmd_mox: CmdMox) -> None:
    """The namespace and warning policy travel with the module."""
    _stub_policy_tools(cmd_mox)
    activate(cmd_mox)

    main(module="traefik")

    arguments = list(cmd_mox.journal[2].args)
    assert arguments[0] == "test", f"conftest must be asked to test: {arguments}"
    assert "--policy" in arguments, f"a policy directory must be given: {arguments}"
    assert (
        arguments[arguments.index("--policy") + 1]
        == "infra/modules/traefik/policy/plan"
    ), f"the module's plan policy must be used: {arguments}"
    assert "--fail-on-warn" in arguments, (
        f"warnings must fail this module's gate: {arguments}"
    )
    assert arguments[arguments.index("--namespace") + 1] == "traefik.policy.plan", (
        f"the module's policy namespace must be selected: {arguments}"
    )


@pytest.mark.usefixtures("traefik_environment")
def test_exported_plan_is_the_document_conftest_reads(cmd_mox: CmdMox) -> None:
    """The JSON that conftest inspects is the output of ``tofu show``."""
    observed: dict[str, str] = {}

    def conftest_handler(invocation: Invocation) -> Response:
        plan_path = Path(invocation.args[1])
        observed["contents"] = plan_path.read_text(encoding="utf-8")
        return Response(exit_code=0)

    stub_tofu(cmd_mox, {}, {"show": PLAN_JSON})
    cmd_mox.stub("conftest").runs(conftest_handler)
    activate(cmd_mox)

    main(module="traefik")

    assert observed["contents"] == PLAN_JSON, (
        "conftest must read exactly what `tofu show` produced"
    )


def test_flux_policy_passes_inline_data_as_a_file(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inline policy parameters are written out because conftest reads paths."""
    observed: dict[str, str] = {}

    def conftest_handler(invocation: Invocation) -> Response:
        arguments = list(invocation.args)
        data_path = Path(arguments[arguments.index("-d") + 1])
        observed["data"] = data_path.read_text(encoding="utf-8")
        observed["namespace"] = "--namespace" if "--namespace" in arguments else ""
        return Response(exit_code=0)

    monkeypatch.setenv("FLUX_KUBECONFIG_PATH", "/tmp/kubeconfig")
    monkeypatch.setenv("FLUX_POLICY_PARAMS_JSON", '{"allowed": true}')
    stub_tofu(cmd_mox, {}, {"show": PLAN_JSON})
    cmd_mox.stub("conftest").runs(conftest_handler)
    activate(cmd_mox)

    main(module="fluxcd")

    assert observed["data"] == '{"allowed": true}', (
        f"inline parameters must reach conftest: {observed['data']}"
    )
    assert observed["namespace"] == "", (
        "the Flux policy has no namespace, unlike the plan policies"
    )


def test_flux_policy_accepts_a_data_path(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A data path is forwarded to conftest unchanged."""
    data_file = tmp_path / "data.json"
    data_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("FLUX_KUBECONFIG_PATH", "/tmp/kubeconfig")
    monkeypatch.delenv("FLUX_POLICY_PARAMS_JSON", raising=False)
    monkeypatch.setenv("FLUX_POLICY_DATA", str(data_file))
    _stub_policy_tools(cmd_mox)
    activate(cmd_mox)

    main(module="fluxcd")

    arguments = list(cmd_mox.journal[2].args)
    assert arguments[arguments.index("-d") + 1] == str(data_file), (
        f"the supplied data path must be forwarded unchanged: {arguments}"
    )


MODULES_WITH_POLICY_DATA = tuple(
    sorted(
        key
        for key, module in MODULES.items()
        if module.policy is not None
        and (module.policy.inline_data_env or module.policy.data_path_env)
    )
)


def _observe_conftest(mox: CmdMox, observed: dict[str, typ.Any]) -> None:
    """Record conftest's arguments and any data file it was handed.

    The data file is read here because the gate deletes its workspace as soon
    as the run finishes. Its contents are compared but never reported, so a
    failing assertion cannot print policy data into a log.
    """

    def handler(invocation: Invocation) -> Response:
        arguments = list(invocation.args)
        observed["arguments"] = arguments
        if "-d" in arguments:
            data_path = Path(arguments[arguments.index("-d") + 1])
            observed["data_path"] = data_path
            observed["data"] = (
                data_path.read_text(encoding="utf-8") if data_path.is_file() else None
            )
        return Response(exit_code=0)

    mox.stub("conftest").runs(handler)


@pytest.mark.parametrize("key", MODULES_WITH_POLICY_DATA, ids=str)
def test_a_configured_data_path_reaches_conftest(
    key: str, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A supplied path is forwarded unchanged."""
    module = MODULES[key]
    policy = module.policy
    assert policy is not None and policy.data_path_env, f"{key} declares no data path"

    data_file = tmp_path / "data.json"
    data_file.write_text("{}", encoding="utf-8")
    for name, value in module_environment(module).items():
        monkeypatch.setenv(name, value)
    if policy.inline_data_env:
        monkeypatch.delenv(policy.inline_data_env, raising=False)
    monkeypatch.setenv(policy.data_path_env, str(data_file))

    observed: dict[str, typ.Any] = {}
    stub_tofu(cmd_mox, {}, {"show": PLAN_JSON})
    _observe_conftest(cmd_mox, observed)
    activate(cmd_mox)

    main(module=key)

    assert observed["data_path"] == data_file, (
        f"{key} did not forward the configured data path: {observed['data_path']}"
    )


@pytest.mark.parametrize("key", MODULES_WITH_POLICY_DATA, ids=str)
def test_inline_data_wins_over_a_configured_path(
    key: str, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With both set, conftest reads the inline parameters, not the path.

    The precedence is documented and was inherited from the Flux policy shell
    script, but nothing pinned it while both values were set at once.
    """
    module = MODULES[key]
    policy = module.policy
    assert policy is not None, f"{key} declares no policy"
    if not (policy.inline_data_env and policy.data_path_env):
        pytest.skip(f"{key} declares only one policy-data source")

    unused_path = tmp_path / "unused.json"
    unused_path.write_text("{}", encoding="utf-8")
    inline = '{"allowed": true}'
    for name, value in module_environment(module).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(policy.inline_data_env, inline)
    monkeypatch.setenv(policy.data_path_env, str(unused_path))

    observed: dict[str, typ.Any] = {}
    stub_tofu(cmd_mox, {}, {"show": PLAN_JSON})
    _observe_conftest(cmd_mox, observed)
    activate(cmd_mox)

    main(module=key)

    assert observed["data_path"] != unused_path, (
        f"{key} used the configured path while inline parameters were set"
    )
    # The value itself is not reported, so a failure cannot leak policy data.
    assert observed["data"] == inline, (
        f"{key} did not hand conftest the inline parameters"
    )
