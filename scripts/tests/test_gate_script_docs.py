"""The scripts' documented examples must run and produce what they claim.

Repository policy is that function documentation carries an example
showing usage and outcome. An example that has drifted from the code is
worse than none, so every example in every module under `scripts` is
executed here.

This module holds the questions about coverage: that the walk finds what
is on disk, that it leaves the suite to pytest, that the two exemption
lists still describe the repository, and that every module neither list
names has examples that hold. Where those examples are allowed to write
is :mod:`scripts.tests.test_gate_script_docs_host_writes`, and the
proof that the write rules bite is
:mod:`scripts.tests.test_gate_script_docs_rules`.
"""

from __future__ import annotations

import pytest

from scripts.tests.gate_script_docs_support import (
    CHECKED_MODULES,
    GATE_MODULES,
    KNOWN_STALE_EXAMPLES,
    NOT_OURS_TO_IMPORT,
    PACKAGE_ROOT,
    REPOSITORY_ROOT,
    SUITE_SUPPORT_MODULES,
    SUPPORT_SUFFIX,
    Verdict,
    run_examples,
)


def test_the_discovered_set_is_exactly_the_eligible_files() -> None:
    """Discovery is compared against an independently built answer.

    `_module_names` is one expression, and a test that called it and
    agreed with itself would assert nothing. This builds the expected
    set the other way round, from the files on disk, so a change to
    either has to be made in both places to go unnoticed.
    """
    expected = {
        ".".join(path.relative_to(REPOSITORY_ROOT).with_suffix("").parts)
        for path in PACKAGE_ROOT.rglob("*.py")
        if path.stem not in NOT_OURS_TO_IMPORT
        and "tests" not in path.relative_to(PACKAGE_ROOT).parts[:-1]
    }

    assert set(GATE_MODULES) == expected, (
        f"discovery disagrees with the files on disk: "
        f"missing {sorted(expected - set(GATE_MODULES))}, "
        f"unexpected {sorted(set(GATE_MODULES) - expected)}"
    )


def test_every_exemption_names_a_discovered_module() -> None:
    """The exemption list is a subset of what the walk found.

    Stated over the whole list as well as per entry, because a
    parametrised test reports one failure per name and this reports the
    shape: an exemption naming something outside the walk is a list
    that has stopped describing the repository.
    """
    strays = sorted(set(KNOWN_STALE_EXAMPLES) - set(GATE_MODULES))

    assert not strays, f"exempted but not discovered: {strays}"


def test_something_is_actually_checked() -> None:
    """The checked set is not empty.

    Every module could in principle be exempted, at which point the
    gate would pass by having nothing to do. That is the failure this
    whole file is meant to prevent, so it is asserted rather than
    assumed.
    """
    assert CHECKED_MODULES, "every discovered module is exempted; the gate is inert"
    exempted = len(KNOWN_STALE_EXAMPLES)
    assert len(CHECKED_MODULES) > exempted, (
        f"{exempted} exempted against {len(CHECKED_MODULES)} checked; "
        "the exemption lists have taken over"
    )


def test_the_walk_leaves_the_suite_to_pytest() -> None:
    """No module this gate imports is one pytest has already imported.

    The walk found every `.py` under `scripts`, which includes the
    thirty-eight modules of this suite. Importing them again under
    `scripts.tests.*` re-runs every module-level statement against a
    second module object, so a fixture registration, a `sys.path` edit
    or a decorator runs twice with the two copies unable to see each
    other.

    It is also a trap rather than merely untidy: three modules here
    import `cmd_mox` at module level, and `conftest` registers its
    plugin only when it is installed, so a narrower invocation may omit
    it. Under such an invocation the second import raises, and this
    gate would report a missing package as a stale example.
    """
    intruders = [name for name in GATE_MODULES if ".tests." in f"{name}."]

    assert not intruders, (
        f"the walk reached {len(intruders)} module(s) of this suite, which "
        f"pytest has already imported: {intruders[:3]}"
    )


def test_the_walk_still_reaches_the_scripts_themselves() -> None:
    """Scoping the walk must not empty it.

    A filter that excluded everything would satisfy the rule above on
    its own, so the two are asserted together. The named module is one
    of the scripts the gate exists for.
    """
    assert len(GATE_MODULES) > 20, GATE_MODULES
    assert "scripts.lint_actions" in GATE_MODULES, GATE_MODULES


@pytest.mark.parametrize("module_name", CHECKED_MODULES, ids=str)
def test_documented_examples_hold(module_name: str) -> None:
    """Every doctest in the module runs and matches its stated output."""
    outcome = run_examples(module_name)

    assert outcome.held, f"{module_name}: {outcome.verdict} - {outcome.detail}"


@pytest.mark.parametrize("module_name", sorted(KNOWN_STALE_EXAMPLES), ids=str)
def test_a_listed_module_is_still_stale(module_name: str) -> None:
    """A module on the known-stale list must still have stale examples.

    This is what stops the list outliving the problem. Without it a
    repaired module keeps its exemption, and the next module to break
    could simply be added beside it. Failing here is good news: remove
    the entry.

    Presence is checked before the reason, and separately, because a
    module that has been deleted or renamed fails to import, an import
    failure is a reason, and a reason is what this test is looking for.
    An exemption for a module that no longer exists would therefore
    satisfy the shrink-only rule forever, which is the one way the list
    can outlive the problem without anyone noticing.
    """
    assert module_name in GATE_MODULES, (
        f"{module_name} is exempted but no longer discovered. Remove it from "
        "KNOWN_STALE_EXAMPLES: an exemption for a module that is gone can "
        "never be retired by repairing it."
    )

    outcome = run_examples(module_name)

    assert outcome.verdict is not Verdict.NOT_IMPORTABLE, (
        f"{module_name} is exempted for stale examples but does not import at "
        f"all: {outcome.detail}. That is a different fault and this list is "
        "not where it belongs."
    )
    assert outcome.verdict is Verdict.STALE, (
        f"{module_name} now passes its own examples ({outcome.detail}). Remove "
        "it from KNOWN_STALE_EXAMPLES; the list is allowed to shrink only."
    )


def test_the_suite_has_support_modules_to_check() -> None:
    """Discovery of this suite's helper modules is not empty.

    The list it replaces named three by hand. A glob that matched
    nothing would satisfy the parametrised test below by having no cases
    at all, which is the way this coverage was lost the first time.

    Kept beside the equality below rather than folded into it, because
    the two refuse different things. Equality refuses a discovery that
    disagrees with the directory; this refuses a directory and a
    discovery that are empty together, which equality accepts.
    """
    assert SUITE_SUPPORT_MODULES, (
        "no support module was discovered, so the parametrised test below "
        "has no cases and asserts nothing"
    )


def test_the_discovered_support_set_is_exactly_the_helper_files() -> None:
    """Support discovery is compared against an independently built answer.

    `_support_module_names` is one expression, and a test that called it
    and agreed with itself would assert nothing. The expected set is
    built the other way round, from the files on disk, so a change to
    either has to be made in both places to go unnoticed. This is the
    same shape as `test_the_discovered_set_is_exactly_the_eligible_files`
    and for the same reason.

    A floor on the count is not this assertion. Discovery could drop
    every support module but three and still clear a floor, which is
    exactly the silent loss this gate exists to notice: the hand list it
    replaced had three entries while the directory held more.
    """
    here = PACKAGE_ROOT / "tests"
    expected = {
        ".".join(path.relative_to(REPOSITORY_ROOT).with_suffix("").parts)
        for path in here.iterdir()
        if path.is_file() and path.name.endswith(SUPPORT_SUFFIX)
    }

    assert set(SUITE_SUPPORT_MODULES) == expected, (
        f"support discovery disagrees with the files on disk: "
        f"missing {sorted(expected - set(SUITE_SUPPORT_MODULES))}, "
        f"unexpected {sorted(set(SUITE_SUPPORT_MODULES) - expected)}"
    )


@pytest.mark.parametrize("module_name", SUITE_SUPPORT_MODULES, ids=str)
def test_a_support_module_of_this_suite_holds_its_examples(module_name: str) -> None:
    """This suite's own helpers are checked, unlike its test modules.

    `scripts/tests` holds two kinds of file and the walk's exclusion
    treated them as one. A test module is pytest's: importing it again
    under a dotted name runs its registrations a second time against a
    second module object. A support module is an ordinary library the
    test modules import, nothing else claims it, and its examples are as
    much documentation as any script's.

    The hand list this gate replaced named three support modules and ran
    them. The walk dropped the whole directory, and the exclusion's
    stated replacement, `--doctest-modules` on the suite's own
    invocation, does not exist: no pytest invocation in this repository
    passes that flag and there is no configuration file to carry it.
    Twenty-eight example lines stopped running and the gate reported
    nothing, which is the failure this whole file exists to prevent
    happening to the scripts.

    Run through `run_examples` rather than a separate importer, so these
    get the same scratch directory and the same environment restore as
    everything else.
    """
    outcome = run_examples(module_name)

    assert outcome.held, f"{module_name}: {outcome.verdict} - {outcome.detail}"
