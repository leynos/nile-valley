#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9", "plumbum"]
# ///
"""Spell-check the tracked Markdown files with typos.

The Make recipe piped `git ls-files` into `xargs typos`. Without `pipefail`
the pipeline reported only the last stage's status, so a failure to list the
files would have been read as a clean spelling run. Listing and checking here
keeps both statuses.

Only tracked files are checked, so a new file must be staged before the gate
can see it.
"""

from __future__ import annotations

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
    capture_tool,
    require_tools,
    run_gate,
    run_tool,
    skip,
)

GIT = "git"
UV = "uv"
DEFAULT_CONFIG = Path("typos.toml")
MARKDOWN_GLOB = "*.md"

app = App(
    name="check-spelling",
    help="Spell-check the tracked Markdown files.",
    config=cyclopts.config.Env("INPUT_", command=False),
)


def tracked_markdown_files(glob: str = MARKDOWN_GLOB) -> list[str]:
    """Return the tracked paths matching ``glob``, in Git's order.

    Examples
    --------
    >>> "README.md" in tracked_markdown_files()
    True
    """
    listing = capture_tool(
        GIT, ["ls-files", "-z", glob], ToolRun(cwd=REPO_ROOT, label="git ls-files")
    )
    return [path for path in listing.split("\0") if path]


@app.default
def main(
    *,
    typos_version: typ.Annotated[str, Parameter(required=True)],
    config: Path = DEFAULT_CONFIG,
    glob: str = MARKDOWN_GLOB,
) -> None:
    """Run typos over every tracked Markdown file.

    Examples
    --------
    >>> # main(typos_version="1.48.0")
    """
    require_tools([GIT, UV])
    files = tracked_markdown_files(glob)
    if not files:
        skip(f"No tracked files match {glob}; skipping the spelling gate")
        return

    run_tool(
        UV,
        [
            "tool",
            "run",
            f"typos@{typos_version}",
            "--config",
            str(config),
            "--force-exclude",
            *files,
        ],
        ToolRun(cwd=REPO_ROOT, label=f"typos@{typos_version}"),
    )


if __name__ == "__main__":
    run_gate(app)
