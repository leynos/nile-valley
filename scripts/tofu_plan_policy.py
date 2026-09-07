#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9", "plumbum"]
# ///
"""Plan a module's OpenTofu example and check the plan with conftest.

The Make recipes performed an environment check, a plan, a JSON export and a
conftest run from one shell line. Only the last command's status reached Make
unless the line happened to enable ``errexit``. Running the sequence here
stops at the first failure and names the step that failed.

The plan artefacts are written to a temporary directory so a failed run
cannot leave a stale plan behind for the next one to check.
"""

from __future__ import annotations

import os
import sys
import tempfile
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._gate_runner import (  # noqa: E402
    GateError,
    ToolRun,
    capture_tool,
    require_env,
    require_tools,
    run_gate,
    run_tool,
    skip,
)
from scripts._tofu_modules import get_module  # noqa: E402

if typ.TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts._tofu_modules import PolicyCheck, TofuModule

TOFU = "tofu"
CONFTEST = "conftest"
AUTOMATION_ENV = {"TF_IN_AUTOMATION": "1"}
PLAN_EXIT_CODES = (0, 2)

app = App(
    name="tofu-plan-policy",
    help="Plan an OpenTofu example and check the plan against its policy.",
    config=cyclopts.config.Env("INPUT_", command=False),
)


def write_plan(module: TofuModule, destination: Path) -> None:
    """Write a binary plan for ``module`` to ``destination``.

    Examples
    --------
    >>> # write_plan(get_module("traefik"), Path("/tmp/tfplan.binary"))
    """
    arguments = [
        f"-chdir={module.example_dir}",
        "plan",
        "-input=false",
        "-no-color",
        f"-out={destination}",
        "-detailed-exitcode",
        *module.var_arguments(module.plan_vars),
    ]
    run_tool(
        TOFU,
        arguments,
        ToolRun(
            cwd=REPO_ROOT,
            env=AUTOMATION_ENV,
            allowed_exit_codes=PLAN_EXIT_CODES,
            label=f"tofu plan ({module.key})",
        ),
    )


def export_plan(module: TofuModule, plan_binary: Path, destination: Path) -> None:
    """Export ``plan_binary`` as JSON for conftest.

    Examples
    --------
    >>> # export_plan(get_module("traefik"), binary, Path("/tmp/plan.json"))
    """
    rendered = capture_tool(
        TOFU,
        [f"-chdir={module.example_dir}", "show", "-json", str(plan_binary)],
        ToolRun(
            cwd=REPO_ROOT,
            env=AUTOMATION_ENV,
            label=f"tofu show ({module.key})",
        ),
    )
    destination.write_text(rendered, encoding="utf-8")


def _inline_data_arguments(
    policy: PolicyCheck, workspace: Path, environ: Mapping[str, str]
) -> list[str]:
    """Return ``-d`` arguments for inline policy parameters.

    conftest reads data from a path, so inline JSON is written into
    ``workspace`` first.

    Examples
    --------
    >>> # _inline_data_arguments(policy, workspace, {})
    """
    inline = environ.get(policy.inline_data_env) if policy.inline_data_env else None
    if not inline:
        return []
    data_file = workspace / "policy-data.json"
    data_file.write_text(inline, encoding="utf-8")
    return ["-d", str(data_file)]


def _data_path_arguments(policy: PolicyCheck, environ: Mapping[str, str]) -> list[str]:
    """Return ``-d`` arguments for a policy data path supplied by the operator.

    Examples
    --------
    >>> # _data_path_arguments(policy, {})
    """
    data_path = environ.get(policy.data_path_env) if policy.data_path_env else None
    return ["-d", data_path] if data_path else []


def _data_arguments(
    policy: PolicyCheck, workspace: Path, environ: Mapping[str, str] | None = None
) -> list[str]:
    """Return conftest ``-d`` arguments for the module's policy data.

    Inline parameters take precedence over a supplied path, matching the
    behaviour the Flux policy shell script had.

    Examples
    --------
    >>> # _data_arguments(policy, Path("/tmp/workspace"))
    """
    environ = os.environ if environ is None else environ
    return _inline_data_arguments(policy, workspace, environ) or _data_path_arguments(
        policy, environ
    )


def check_plan(module: TofuModule, plan_json: Path, workspace: Path) -> None:
    """Run conftest against the exported plan.

    Examples
    --------
    >>> # check_plan(get_module("traefik"), plan_json, workspace)
    """
    policy = module.policy
    if policy is None:  # pragma: no cover - guarded by main()
        message = f"module {module.key} has no plan policy"
        raise GateError(message)

    arguments = ["test", str(plan_json), "--policy", str(policy.policy_dir)]
    if policy.fail_on_warn:
        arguments.append("--fail-on-warn")
    if policy.namespace:
        arguments.extend(["--namespace", policy.namespace])
    arguments.extend(_data_arguments(policy, workspace))

    run_tool(
        CONFTEST,
        arguments,
        ToolRun(cwd=REPO_ROOT, label=f"conftest ({module.key} plan policy)"),
    )


@app.default
def main(*, module: typ.Annotated[str, Parameter(required=True)]) -> None:
    """Plan ``module``'s example and check the plan when the gate is enabled.

    Examples
    --------
    >>> # main(module="traefik")
    """
    configuration = get_module(module)
    if configuration.policy is None:
        message = f"module {module} has no plan policy"
        raise GateError(message)

    require_tools([TOFU, CONFTEST])

    if not configuration.is_enabled():
        skip(f"Skipping {module} plan policy; set {configuration.gate_env} to run")
        return

    require_env(
        configuration.missing_requirements(),
        because=f"when {configuration.gate_env} is set",
    )

    with tempfile.TemporaryDirectory(prefix=f"{module}-plan-policy-") as raw:
        workspace = Path(raw)
        plan_binary = workspace / "tfplan.binary"
        plan_json = workspace / "plan.json"
        write_plan(configuration, plan_binary)
        export_plan(configuration, plan_binary, plan_json)
        check_plan(configuration, plan_json, workspace)


if __name__ == "__main__":
    run_gate(app)
