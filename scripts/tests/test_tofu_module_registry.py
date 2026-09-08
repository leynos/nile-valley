"""Every registered OpenTofu module is driven through both gate scripts.

The registry is a finite, known set, so it is parametrized exhaustively rather
than sampled. Each module is exercised for its example path, its opt-in gate
variable, its required companion variables, the `-var` assignments it passes
to validate and plan, and the conftest options its policy declares.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import GateError
from scripts._tofu_modules import MODULES
from scripts.tests.gate_test_support import activate, commands_run
from scripts.tests.tofu_gate_test_support import (
    module_environment,
    stub_tofu,
    tofu_calls,
)
from scripts.tofu_example_gate import main as example_gate
from scripts.tofu_plan_policy import main as plan_policy

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

    from scripts._tofu_modules import TofuModule

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

MODULE_KEYS = tuple(sorted(MODULES))
MODULES_WITH_REQUIREMENTS = tuple(
    sorted(key for key, module in MODULES.items() if module.required_env)
)
MODULES_WITHOUT_REQUIREMENTS = tuple(
    sorted(key for key, module in MODULES.items() if not module.required_env)
)
PLAN_JSON = '{"resource_changes": []}'


def _module(key: str) -> TofuModule:
    """Return the registered module for ``key``."""
    return MODULES[key]


def _enable(monkeypatch: pytest.MonkeyPatch, module: TofuModule) -> dict[str, str]:
    """Set every variable ``module`` declares and return the values used."""
    environment = module_environment(module)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return environment


def _var_assignments(arguments: list[str]) -> list[str]:
    """Return the `-var` assignments from an OpenTofu argument list."""
    return [
        argument
        for index, argument in enumerate(arguments)
        if index > 0 and arguments[index - 1] == "-var"
    ]


@pytest.mark.parametrize("key", MODULE_KEYS, ids=str)
def test_example_directory_exists(key: str) -> None:
    """The registry points at an example that is in the repository."""
    module = _module(key)

    assert module.example_path.is_dir(), (
        f"{key} names {module.example_dir}, which is not a directory"
    )


@pytest.mark.parametrize("key", MODULE_KEYS, ids=str)
def test_gate_is_opt_in(
    key: str,
    cmd_mox: CmdMox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without its kubeconfig variable the module's gate skips and runs nothing."""
    module = _module(key)
    monkeypatch.delenv(module.gate_env, raising=False)
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    example_gate(module=key)

    output = capsys.readouterr().out
    assert module.gate_env in output, f"the skip must name {module.gate_env}: {output}"
    assert commands_run(cmd_mox) == [], f"{key} ran a tool while disabled"


@pytest.mark.parametrize("key", MODULES_WITH_REQUIREMENTS, ids=str)
def test_every_required_variable_is_reported(
    key: str, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An enabled gate with no companion variables names all of them at once."""
    module = _module(key)
    monkeypatch.setenv(module.gate_env, "/tmp/kubeconfig")
    for name in module.required_env:
        monkeypatch.delenv(name, raising=False)
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        example_gate(module=key)

    message = str(excinfo.value)
    for name in module.required_env:
        assert name in message, f"{name} is required by {key} but unnamed: {message}"
    assert commands_run(cmd_mox) == [], f"{key} planned with an incomplete environment"


@pytest.mark.parametrize("key", MODULES_WITHOUT_REQUIREMENTS, ids=str)
def test_module_without_requirements_proceeds(
    key: str, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module declaring no companion variables runs on the kubeconfig alone."""
    module = _module(key)
    monkeypatch.setenv(module.gate_env, "/tmp/kubeconfig")
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    example_gate(module=key)

    assert tofu_calls(cmd_mox) == ["validate", "plan"], (
        f"{key} should validate and plan without companion variables"
    )


@pytest.mark.parametrize("key", MODULE_KEYS, ids=str)
def test_declared_variables_reach_validate_and_plan(
    key: str, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each declared assignment is passed, with the module's example selected."""
    module = _module(key)
    environment = _enable(monkeypatch, module)
    stub_tofu(cmd_mox)
    activate(cmd_mox)

    example_gate(module=key)

    chdir = f"-chdir={module.example_dir}"
    for invocation, variables in (
        (cmd_mox.journal[0], module.validate_vars),
        (cmd_mox.journal[1], module.plan_vars),
    ):
        arguments = list(invocation.args)
        assert arguments[0] == chdir, f"{key} must select its example: {arguments[0]}"
        assignments = _var_assignments(arguments)
        expected = [
            f"{variable.name}={environment[variable.env_var]}"
            for variable in variables
        ]
        assert assignments == expected, (
            f"{key} passed {assignments}, expected {expected}"
        )


@pytest.mark.parametrize("key", MODULE_KEYS, ids=str)
def test_policy_options_match_the_registry(
    key: str, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """conftest receives the policy directory, namespace and warning policy."""
    module = _module(key)
    policy = module.policy
    assert policy is not None, f"{key} declares no plan policy"

    _enable(monkeypatch, module)
    for name in (policy.inline_data_env, policy.data_path_env):
        if name:
            monkeypatch.delenv(name, raising=False)
    stub_tofu(cmd_mox, {}, {"show": PLAN_JSON})
    cmd_mox.stub("conftest").returns(exit_code=0)
    activate(cmd_mox)

    plan_policy(module=key)

    arguments = list(cmd_mox.journal[2].args)
    assert arguments[arguments.index("--policy") + 1] == str(policy.policy_dir), (
        f"{key} must check its own policy directory: {arguments}"
    )
    assert ("--fail-on-warn" in arguments) is policy.fail_on_warn, (
        f"{key} declares fail_on_warn={policy.fail_on_warn}: {arguments}"
    )
    if policy.namespace:
        assert arguments[arguments.index("--namespace") + 1] == policy.namespace, (
            f"{key} must select {policy.namespace}: {arguments}"
        )
    else:
        assert "--namespace" not in arguments, (
            f"{key} declares no namespace, so none may be passed: {arguments}"
        )
    assert "-d" not in arguments, (
        f"{key} was given policy data it did not declare: {arguments}"
    )


def test_the_registry_is_read_only() -> None:
    """A caller cannot replace a module's configuration.

    The registry is imported wherever a gate runs, so a mutable mapping would
    let any importer change what another gate plans.
    """
    with pytest.raises(TypeError):
        MODULES["traefik"] = MODULES["fluxcd"]  # type: ignore[index]


@pytest.mark.parametrize("key", MODULE_KEYS, ids=str)
def test_enablement_reads_only_the_given_environment(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module decides from the mapping it is handed, not from the process.

    The gate scripts capture the environment once at the command line and pass
    it down, so a function that reached for ``os.environ`` would make a
    decision the caller cannot see or reproduce.
    """
    module = _module(key)
    monkeypatch.setenv(module.gate_env, "/tmp/kubeconfig")

    assert not module.is_enabled({}), (
        f"{key} read the ambient environment rather than the mapping given"
    )
    assert module.is_enabled({module.gate_env: "/tmp/kubeconfig"}), (
        f"{key} ignored the mapping it was given"
    )


@pytest.mark.parametrize("key", MODULES_WITH_REQUIREMENTS, ids=str)
def test_requirements_read_only_the_given_environment(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Companion variables are read from the mapping, not the process."""
    module = _module(key)
    for name in module.required_env:
        monkeypatch.setenv(name, "set-in-the-process")

    missing = module.missing_requirements({})

    assert all(value is None for value in missing.values()), (
        f"{key} read companion variables from the ambient environment: {missing}"
    )


@pytest.mark.parametrize("key", MODULE_KEYS, ids=str)
def test_var_arguments_read_only_the_given_environment(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `-var` assignment carries the value from the mapping given."""
    module = _module(key)
    environment = module_environment(module)
    for name in environment:
        monkeypatch.setenv(name, "from-the-process")

    arguments = module.var_arguments(module.plan_vars, environment)

    assert "from-the-process" not in " ".join(arguments), (
        f"{key} took a value from the ambient environment: {arguments}"
    )
