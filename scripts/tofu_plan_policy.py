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

import dataclasses as dc
import os
import sys
import tempfile
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # The repository root has to be on the path before the `scripts` package
    # can be imported, which is why this import cannot sit with the others.
    sys.path.insert(0, str(REPO_ROOT))

from scripts._gate_runner import (  # noqa: E402  # see the sys.path note above
    GateError,
    ToolRun,
    capture_tool,
    require_env,
    require_tools,
    run_gate,
    run_tool,
    skip,
)
from scripts._tofu_modules import get_module  # noqa: E402  # see above

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


@dc.dataclass(frozen=True, slots=True)
class PolicyData:
    """Where conftest should read the module's policy data from.

    Exactly one of the fields is set, or neither when the module declares no
    policy data. ``inline`` still has to be written to a file before conftest
    can read it, which is :func:`write_policy_data`'s job.

    Examples
    --------
    >>> PolicyData(path="data.json").arguments()
    ['-d', 'data.json']
    """

    inline: str | None = None
    path: str | None = None

    def arguments(self) -> list[str]:
        """Return the conftest ``-d`` arguments for an already-readable path.

        Examples
        --------
        >>> PolicyData().arguments()
        []
        """
        return ["-d", self.path] if self.path else []


def select_policy_data(
    policy: PolicyCheck, environ: Mapping[str, str] | None = None
) -> PolicyData:
    """Return the policy data the environment selects, reading nothing.

    Inline parameters take precedence over a supplied path, matching the
    behaviour of the Flux policy shell script this replaced.

    Examples
    --------
    >>> select_policy_data(get_module("fluxcd").policy, {})
    PolicyData(inline=None, path=None)
    """
    environ = os.environ if environ is None else environ

    inline = environ.get(policy.inline_data_env) if policy.inline_data_env else None
    if inline:
        return PolicyData(inline=inline)

    path = environ.get(policy.data_path_env) if policy.data_path_env else None
    return PolicyData(path=path or None)


def write_policy_data(data: PolicyData, workspace: Path) -> PolicyData:
    """Write inline data into ``workspace`` and return a readable descriptor.

    conftest reads data from a path rather than from a literal, so inline
    parameters become a file here. A descriptor that already names a path is
    returned unchanged.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as raw:
    ...     written = write_policy_data(PolicyData(inline="{}"), Path(raw))
    ...     Path(written.path).read_text(encoding="utf-8")
    '{}'
    """
    if data.inline is None:
        return data

    data_file = workspace / "policy-data.json"
    data_file.write_text(data.inline, encoding="utf-8")
    return PolicyData(path=str(data_file))


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
    readable = write_policy_data(select_policy_data(policy), workspace)
    arguments.extend(readable.arguments())

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
