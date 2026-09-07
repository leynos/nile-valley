"""Contract: every gate variable the scripts read reaches them from Make.

The gate scripts read their configuration from the environment. Make does not
export a variable set on its command line unless the Makefile says so, so
`make traefik-test TRAEFIK_KUBECONFIG_PATH=...` would otherwise be silently
ignored and the gate would report a skip.

The first test derives the variable names from the registry rather than from a
list written by hand, so a new module cannot be added without its variables
being covered. The second runs Make for real and reads the value out of a
child process.
"""

from __future__ import annotations

import re
import subprocess
import typing as typ

import pytest
from makefile_contract_support import REPO_ROOT

from scripts._tofu_modules import MODULES

if typ.TYPE_CHECKING:
    from pathlib import Path

    from scripts._tofu_modules import TofuModule

EXPORT_PREFIX = "export "
CONTINUATION = re.compile(r"\\\n")
PROBE_TARGET = "gate-environment-probe"


def _module_environment(module: TofuModule) -> set[str]:
    """Return every environment variable name ``module`` reads."""
    names = {module.gate_env, *module.required_env}
    for variable in (*module.validate_vars, *module.plan_vars):
        names.add(variable.env_var)
    if module.policy is not None:
        names.update(
            name
            for name in (module.policy.inline_data_env, module.policy.data_path_env)
            if name
        )
    return names


def registry_environment() -> tuple[str, ...]:
    """Return every environment variable name the module registry reads."""
    names: set[str] = set()
    for module in MODULES.values():
        names |= _module_environment(module)
    return tuple(sorted(names))


def exported_names() -> frozenset[str]:
    """Return the variable names the Makefile marks for export."""
    names: set[str] = set()
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for line in CONTINUATION.sub(" ", text).splitlines():
        if line.startswith(EXPORT_PREFIX):
            names.update(line[len(EXPORT_PREFIX) :].split())
    return frozenset(names)


@pytest.mark.parametrize("name", registry_environment(), ids=str)
def test_every_gate_variable_is_exported(name: str) -> None:
    """A variable the registry reads is marked for export in the Makefile."""
    assert name in exported_names(), (
        f"{name} is read by the module registry but the Makefile does not "
        "export it, so a `make <target> VAR=value` override would be lost"
    )


def test_no_stale_exports() -> None:
    """The export list holds nothing the registry has stopped reading."""
    stale = exported_names() - set(registry_environment())
    assert stale == set(), f"the Makefile exports variables nothing reads: {stale}"


@pytest.mark.parametrize("name", registry_environment(), ids=str)
def test_command_line_override_reaches_a_child_process(
    name: str, tmp_path: Path
) -> None:
    """`make <target> VAR=value` is visible to the process Make starts.

    A probe makefile is loaded after the repository's own, so the export
    directives under test are the real ones.
    """
    probe = tmp_path / "probe.mk"
    probe.write_text(
        f".PHONY: {PROBE_TARGET}\n{PROBE_TARGET}:\n\t@printenv {name}\n",
        encoding="utf-8",
    )

    completed = subprocess.run(  # noqa: S603
        [
            "make",
            "--file",
            "Makefile",
            "--file",
            str(probe),
            "--no-print-directory",
            PROBE_TARGET,
            f"{name}=probe-value",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        f"the probe could not read {name}: {completed.stderr.strip()}"
    )
    assert completed.stdout.strip() == "probe-value", (
        f"{name} did not reach the child process: {completed.stdout!r}"
    )
