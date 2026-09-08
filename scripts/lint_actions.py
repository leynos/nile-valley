#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9", "plumbum"]
# ///
"""Lint composite actions and workflows with yamllint, action-validator and actionlint.

Make previously ran these tools from a single shell line, so yamllint's exit
status was discarded and only the last tool decided the gate. Running them
from one script stops at the first failing tool and names it.

The directory defaults are relative because Make invokes this script from the
repository root.
"""

from __future__ import annotations

import sys
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # The repository root has to be on the path before the `scripts` package
    # can be imported, which is why this import cannot sit with the others.
    sys.path.insert(0, str(REPO_ROOT))

from scripts._gate_runner import (  # noqa: E402  # see the sys.path note above
    ToolRun,
    require_tools,
    run_gate,
    run_tool,
    skip,
)

if typ.TYPE_CHECKING:
    from collections.abc import Sequence

ACTION_MANIFEST_NAME = "action.yml"
WORKFLOW_SUFFIXES = (".yml", ".yaml")
REQUIRED_TOOLS = ("yamllint", "action-validator", "actionlint")

app = App(
    name="lint-actions",
    help="Lint composite action manifests and workflow files.",
    config=cyclopts.config.Env("INPUT_", command=False),
)


def _as_arguments(paths: Sequence[Path]) -> list[str]:
    """Render ``paths`` as command-line arguments."""
    return [str(path) for path in paths]


def lint_composite_actions(actions_dir: Path) -> None:
    """Lint every composite action manifest under ``actions_dir``.

    yamllint runs across all manifests first; action-validator then checks each
    manifest in turn. A failure in either tool aborts before the next runs.

    Examples
    --------
    >>> # lint_composite_actions(Path(".github/actions"))
    """
    if not actions_dir.is_dir():
        skip("No composite actions found; skipping composite action lint")
        return

    manifests = sorted(actions_dir.rglob(ACTION_MANIFEST_NAME))
    if not manifests:
        skip("No composite action manifests found; skipping composite action lint")
        return

    run_tool(
        "yamllint",
        _as_arguments(manifests),
        ToolRun(label="yamllint (composite actions)"),
    )
    for manifest in manifests:
        print(f"{manifest}:", flush=True)
        run_tool(
            "action-validator",
            [str(manifest)],
            ToolRun(label=f"action-validator ({manifest})"),
        )


def lint_workflows(workflows_dir: Path) -> None:
    """Lint every workflow file under ``workflows_dir``.

    yamllint enforces the repository's YAML style and actionlint checks the
    workflow semantics; both statuses reach the caller.

    Examples
    --------
    >>> # lint_workflows(Path(".github/workflows"))
    """
    if not workflows_dir.is_dir():
        skip("No workflows found; skipping workflow lint")
        return

    workflows = sorted(
        path
        for path in workflows_dir.rglob("*")
        if path.is_file() and path.suffix in WORKFLOW_SUFFIXES
    )
    if not workflows:
        skip("No workflow files found; skipping workflow lint")
        return

    arguments = _as_arguments(workflows)
    run_tool("yamllint", arguments, ToolRun(label="yamllint (workflows)"))
    run_tool("actionlint", arguments)


@app.default
def main(
    *,
    actions_dir: Path = Path(".github/actions"),
    workflows_dir: Path = Path(".github/workflows"),
) -> None:
    """Run the composite action and workflow lint gate.

    Examples
    --------
    >>> # main(actions_dir=Path(".github/actions"))
    """
    require_tools(REQUIRED_TOOLS)
    lint_composite_actions(actions_dir)
    lint_workflows(workflows_dir)


if __name__ == "__main__":
    run_gate(app)
