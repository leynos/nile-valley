"""Tests for the Helm manifest lint gate.

The gate replaced a `set -o pipefail` shell pipeline in the Makefile. These
tests pin the ordering and the failure handling that the pipeline provided:
a failed render stops the gate, and a yamllint failure is reported.
"""

from __future__ import annotations

import typing as typ

import pytest

from scripts._gate_runner import GateError
from scripts.lint_helm_manifests import main
from scripts.tests.gate_test_support import (
    activate,
    commands_run,
    empty_search_path,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox

pytestmark = pytest.mark.cmd_mox(auto_lifecycle=False)

RENDERED_MANIFEST = "apiVersion: v1\nkind: Service\n"


def test_render_precedes_lint_and_both_pass(cmd_mox: CmdMox) -> None:
    """helm renders the chart and yamllint reads the rendered document."""
    cmd_mox.stub("helm").returns(stdout=RENDERED_MANIFEST, exit_code=0)
    cmd_mox.stub("yamllint").returns(exit_code=0)
    activate(cmd_mox)

    main(release="example-app", kube_version="1.31.0")

    assert commands_run(cmd_mox) == ["helm", "yamllint"]


def test_helm_arguments_carry_the_requested_kube_version(cmd_mox: CmdMox) -> None:
    """The Kubernetes version reaches helm rather than being silently dropped."""
    cmd_mox.stub("helm").returns(stdout=RENDERED_MANIFEST, exit_code=0)
    cmd_mox.stub("yamllint").returns(exit_code=0)
    activate(cmd_mox)

    main(release="example-app", kube_version="1.33.1")

    helm_call = cmd_mox.journal[0]
    assert helm_call.args[:2] == ["template", "example-app"]
    assert "--kube-version" in helm_call.args
    assert helm_call.args[helm_call.args.index("--kube-version") + 1] == "1.33.1"


def test_rendered_output_is_fed_to_yamllint(cmd_mox: CmdMox) -> None:
    """yamllint reads the rendered manifests on standard input."""
    cmd_mox.stub("helm").returns(stdout=RENDERED_MANIFEST, exit_code=0)
    cmd_mox.stub("yamllint").returns(exit_code=0)
    activate(cmd_mox)

    main(release="example-app", kube_version="1.31.0")

    yamllint_call = cmd_mox.journal[1]
    assert yamllint_call.args == ["-f", "parsable", "-"]
    assert yamllint_call.stdin == RENDERED_MANIFEST


def test_failing_render_stops_before_lint(cmd_mox: CmdMox) -> None:
    """A chart that fails to render never reaches yamllint.

    Without `pipefail` the shell pipeline reported yamllint's clean status on
    an empty document, so this is the case the script has to hold.
    """
    cmd_mox.stub("helm").returns(stdout="", exit_code=1)
    cmd_mox.stub("yamllint").returns(exit_code=0)
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(release="example-app", kube_version="1.31.0")

    assert "helm" in str(excinfo.value)
    assert commands_run(cmd_mox) == ["helm"]


def test_failing_lint_is_reported(cmd_mox: CmdMox) -> None:
    """A yamllint finding fails the gate after a successful render."""
    cmd_mox.stub("helm").returns(stdout=RENDERED_MANIFEST, exit_code=0)
    cmd_mox.stub("yamllint").returns(exit_code=1)
    activate(cmd_mox)

    with pytest.raises(GateError) as excinfo:
        main(release="example-app", kube_version="1.31.0")

    assert "yamllint" in str(excinfo.value)
    assert commands_run(cmd_mox) == ["helm", "yamllint"]


def test_missing_tools_are_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both tools are checked before the chart is rendered."""
    with (
        empty_search_path(monkeypatch, tmp_path / "empty-bin"),
        pytest.raises(GateError) as excinfo,
    ):
        main(release="example-app", kube_version="1.31.0")

    message = str(excinfo.value)
    assert "helm" in message
    assert "yamllint" in message
