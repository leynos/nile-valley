#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9", "plumbum"]
# ///
"""Render a Helm chart and lint the resulting manifests with yamllint.

The Make recipe used to enable ``pipefail`` and pipe ``helm template`` into
yamllint on one line. Rendering and linting here keeps both exit statuses:
a chart that fails to render stops the gate before yamllint is handed an
empty document.

The rendered manifests go to a temporary file rather than through this
process, because a chart's size is a property of the chart.
"""

from __future__ import annotations

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
    ToolRun,
    require_tools,
    run_gate,
    run_tool,
    write_tool_output,
)

REQUIRED_TOOLS = ("helm", "yamllint")
DEFAULT_RELEASE = "example-app"
DEFAULT_CHART = Path("deploy/charts/example-app")

app = App(
    name="lint-helm-manifests",
    help="Render a Helm chart and lint the rendered manifests.",
    config=cyclopts.config.Env("INPUT_", command=False),
)


@app.default
def main(
    *,
    release: str = DEFAULT_RELEASE,
    chart: Path = DEFAULT_CHART,
    kube_version: typ.Annotated[str, Parameter(env_var="KUBE_VERSION")] = "1.31.0",
) -> None:
    """Render ``chart`` for ``kube_version`` and lint the output.

    Examples
    --------
    >>> # main(release="example-app", chart=Path("deploy/charts/example-app"))
    """
    require_tools(REQUIRED_TOOLS)
    with tempfile.TemporaryDirectory(prefix="helm-manifests-") as raw:
        rendered = Path(raw) / "rendered.yaml"
        write_tool_output(
            "helm",
            ["template", release, str(chart), "--kube-version", kube_version],
            destination=rendered,
            run=ToolRun(label="helm template"),
        )
        run_tool("yamllint", ["-f", "parsable", "-"], ToolRun(stdin_path=rendered))


if __name__ == "__main__":
    run_gate(app)
