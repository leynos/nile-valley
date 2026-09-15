"""The scripts' documented examples must run and produce what they claim.

Repository policy is that function documentation carries an example showing
usage and outcome. An example that has drifted from the code is worse than
none, so every example in every module under `scripts` is executed here.

The module list is walked rather than written down. The hand-written one
this replaces named eleven modules while thirty-four carried examples,
so 199 of 269 example lines were never run, and adding a module with a
stale example changed nothing a reader would notice.
"""

from __future__ import annotations

import doctest
import importlib
from pathlib import Path

import pytest

#: `conftest.py` is pytest's to import. Importing it a second time under
#: a dotted name would run its `sys.path` setup again against a
#: different module object, so its own examples are left to pytest.
NOT_OURS_TO_IMPORT = frozenset({"conftest", "__init__"})

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent


def _module_names() -> tuple[str, ...]:
    """Return every module under `scripts`, in a stable order.

    Enumerated rather than listed by hand. The list this replaces named
    eleven modules while thirty-four carried examples, and nothing said
    so: adding a module with a stale example left it unchecked, and the
    suite stayed green. A list that cannot be added to cannot drift.

    Returns
    -------
    tuple[str, ...]
        Importable dotted names, sorted so the parametrisation ids are
        stable between runs.
    """
    names = [
        ".".join(path.relative_to(REPOSITORY_ROOT).with_suffix("").parts)
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if path.stem not in NOT_OURS_TO_IMPORT
    ]
    assert names, f"no modules found under {PACKAGE_ROOT}; the walk is wrong"
    return tuple(names)


GATE_MODULES = _module_names()

#: Modules whose examples did not hold when the walk replaced the hand
#: list, on 2026-09-15. Thirty-five examples across these seventeen
#: modules fail, mostly naming functions that have since been renamed or
#: removed. Repairing them is not this branch's work, and turning the
#: gate red on it would be worse than recording it.
#:
#: This list only ever shrinks. `test_a_listed_module_is_still_stale`
#: fails when a listed module starts passing, so a repair cannot leave
#: its entry behind, and nothing adds to the list by accident: a module
#: not named here is checked from the moment it exists. Tracked in
#: leynos/nile-valley#103.
KNOWN_STALE_EXAMPLES = frozenset(
    {
    "scripts._gitops_repo",
    "scripts._infra_k8s_errors",
    "scripts._infra_k8s_github",
    "scripts._infra_k8s_manifests",
    "scripts._infra_k8s_tofu",
    "scripts._prepare_infra_k8s_inputs",
    "scripts._prepare_infra_k8s_models",
    "scripts._provision_cluster_flow",
    "scripts._render_platform_inputs",
    "scripts._vault_bootstrap",
    "scripts._vault_commands",
    "scripts.check_test_dependencies",
    "scripts.generate_typos_config",
    "scripts.publish_infra_k8s_outputs",
    "scripts.render_platform_manifests",
    "scripts.typos_rollout",
    "scripts.typos_rollout_http",
    }
)

CHECKED_MODULES = tuple(m for m in GATE_MODULES if m not in KNOWN_STALE_EXAMPLES)


def _why_examples_fail(module_name: str) -> str | None:
    """Return why a module's examples do not hold, or None if they do.

    Three things go wrong here and only one of them is a wrong expected
    value. A module can fail to import at all, and `doctest` itself can
    refuse a malformed docstring before running anything. Both raise
    rather than returning a count, so a helper that only read
    ``results.failed`` would let them through as a passing run.

    Parameters
    ----------
    module_name : str
        The dotted module name.

    Returns
    -------
    str or None
        A short reason, or None when every example holds.
    """
    try:
        module = importlib.import_module(module_name)
        results = doctest.testmod(
            module, verbose=False, optionflags=doctest.NORMALIZE_WHITESPACE
        )
    except Exception as error:  # noqa: BLE001 - the reason is the answer here
        return f"{type(error).__name__}: {error}"
    if results.failed:
        return f"{results.failed} of {results.attempted} example(s) stale"
    return None


@pytest.mark.parametrize("module_name", CHECKED_MODULES, ids=str)
def test_documented_examples_hold(module_name: str) -> None:
    """Every doctest in the module runs and matches its stated output."""
    reason = _why_examples_fail(module_name)

    assert reason is None, f"{module_name}: {reason}"


@pytest.mark.parametrize("module_name", sorted(KNOWN_STALE_EXAMPLES), ids=str)
def test_a_listed_module_is_still_stale(module_name: str) -> None:
    """A module on the known-stale list must still have stale examples.

    This is what stops the list outliving the problem. Without it a
    repaired module keeps its exemption, and the next module to break
    could simply be added beside it. Failing here is good news: remove
    the entry.
    """
    reason = _why_examples_fail(module_name)

    assert reason is not None, (
        f"{module_name} now passes its own examples. Remove it from "
        "KNOWN_STALE_EXAMPLES; the list is allowed to shrink only."
    )
