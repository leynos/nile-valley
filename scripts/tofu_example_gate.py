#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9", "plumbum"]
# ///
"""Validate and plan a module's OpenTofu example.

The Make recipes ran ``tofu validate`` and ``tofu plan`` from one shell line
and then captured ``$?``, so a validation failure was discarded and only the
plan decided the gate. Running both steps here stops at the first failure and
names the step that failed.

``tofu plan -detailed-exitcode`` returns 2 when changes are pending, which is
expected against a live cluster and is therefore not a failure.
"""

from __future__ import annotations

import os
import sys
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
    ToolRun,
    require_env,
    require_tools,
    run_gate,
    run_tool,
    skip,
)
from scripts._tofu_modules import get_module  # noqa: E402  # see above

if typ.TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts._tofu_modules import TofuModule

TOFU = "tofu"
AUTOMATION_ENV = {"TF_IN_AUTOMATION": "1"}
PLAN_EXIT_CODES = (0, 2)

app = App(
    name="tofu-example-gate",
    help="Validate and plan an OpenTofu module example.",
    config=cyclopts.config.Env("INPUT_", command=False),
)


def validate_example(module: TofuModule, environ: Mapping[str, str]) -> None:
    """Run ``tofu validate`` for ``module``'s example.

    Examples
    --------
    >>> # validate_example(get_module("traefik"), {})
    """
    arguments = [
        f"-chdir={module.example_dir}",
        "validate",
        "-no-color",
        *module.var_arguments(module.validate_vars, environ),
    ]
    run_tool(
        TOFU,
        arguments,
        ToolRun(
            cwd=REPO_ROOT,
            env=AUTOMATION_ENV,
            label=f"tofu validate ({module.key})",
        ),
    )


def plan_example(module: TofuModule, environ: Mapping[str, str]) -> None:
    """Run ``tofu plan`` for ``module``'s example, accepting pending changes.

    Examples
    --------
    >>> # plan_example(get_module("traefik"), {})
    """
    arguments = [
        f"-chdir={module.example_dir}",
        "plan",
        "-input=false",
        "-no-color",
        "-detailed-exitcode",
        *module.var_arguments(module.plan_vars, environ),
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


@app.default
def main(*, module: typ.Annotated[str, Parameter(required=True)]) -> None:
    """Validate and plan ``module``'s example when the gate is enabled.

    Examples
    --------
    >>> # main(module="traefik")
    """
    configuration = get_module(module)
    require_tools([TOFU])

    # The environment is read once, here at the command-line boundary, and
    # passed on explicitly. Nothing below decides from ambient state.
    environ = dict(os.environ)

    if not configuration.is_enabled(environ):
        skip(
            f"Skipping {module} validate and plan; "
            f"set {configuration.gate_env} to enable"
        )
        return

    require_env(
        configuration.missing_requirements(environ),
        because=f"when {configuration.gate_env} is set",
    )
    validate_example(configuration, environ)
    plan_example(configuration, environ)


if __name__ == "__main__":
    run_gate(app)
