"""The gate scripts' documented examples must run and produce what they claim.

Repository policy is that function documentation carries an example showing
usage and outcome. An example that has drifted from the code is worse than
none, so every example in the gate modules is executed here.
"""

from __future__ import annotations

import doctest
import importlib

import pytest

GATE_MODULES = (
    "scripts._gate_runner",
    "scripts._tofu_modules",
    "scripts.check_spelling",
    "scripts.lint_actions",
    "scripts.lint_helm_manifests",
    "scripts.run_bun_tool",
    "scripts.tofu_example_gate",
    "scripts.tofu_plan_policy",
    "scripts.tests.gate_test_support",
    "scripts.tests.makefile_contract_support",
    "scripts.tests.tofu_gate_test_support",
)


@pytest.mark.parametrize("module_name", GATE_MODULES, ids=str)
def test_documented_examples_hold(module_name: str) -> None:
    """Every doctest in the module runs and matches its stated output."""
    module = importlib.import_module(module_name)
    results = doctest.testmod(module, verbose=False)

    assert results.failed == 0, f"{module_name} has {results.failed} stale example(s)"
