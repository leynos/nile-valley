#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9", "plumbum"]
# ///
"""Run a Node-based tool from ``PATH``, falling back to an ephemeral ``bun x``.

The Makefile expressed this choice as a shell conditional inside the recipe.
Gate recipes must be a single command, so the selection lives here and the
tool's exit status is returned to Make unchanged.
"""

from __future__ import annotations

import sys
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._gate_runner import (  # noqa: E402
    require_tools,
    run_gate,
    run_tool,
    tool_path,
)

BUN = "bun"

app = App(
    name="run-bun-tool",
    help="Run a Node-based tool from PATH, or through `bun x` when absent.",
    config=cyclopts.config.Env("INPUT_", command=False),
)


@app.default
def main(
    *arguments: str,
    tool: typ.Annotated[str, Parameter(required=True)],
    package: str | None = None,
) -> None:
    """Run ``tool`` with ``arguments``.

    An installed tool is preferred so a warm CI cache is used; otherwise
    ``bun x`` fetches ``package`` for a single run.

    Examples
    --------
    >>> # main("ci", "scripts", tool="biome", package="@biomejs/biome@2.3.1")
    """
    if tool_path(tool) is not None:
        run_tool(tool, arguments)
        return

    require_tools([BUN])
    bun_arguments = ["x"]
    if package:
        bun_arguments.append(f"--package={package}")
    bun_arguments.extend([tool, *arguments])
    run_tool(BUN, bun_arguments, label=f"bun x {tool}")


if __name__ == "__main__":
    run_gate(app)
