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
    NOT_IMPORTABLE_HERE,
    NOT_OURS_TO_IMPORT,
    PACKAGE_ROOT,
    REPOSITORY_ROOT,
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
    exempted = set(KNOWN_STALE_EXAMPLES) | set(NOT_IMPORTABLE_HERE)
    strays = sorted(exempted - set(GATE_MODULES))

    assert not strays, f"exempted but not discovered: {strays}"


def test_something_is_actually_checked() -> None:
    """The checked set is not empty.

    Every module could in principle be exempted, at which point the
    gate would pass by having nothing to do. That is the failure this
    whole file is meant to prevent, so it is asserted rather than
    assumed.
    """
    assert CHECKED_MODULES, "every discovered module is exempted; the gate is inert"
    exempted = len(KNOWN_STALE_EXAMPLES) + len(NOT_IMPORTABLE_HERE)
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
    plugin only when it is installed, precisely because one gate runs a
    narrower invocation without it. Under such an invocation the second
    import raises, and this gate reports a missing package as a stale
    example.
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
    assert "scripts.check_spelling" in GATE_MODULES, GATE_MODULES


@pytest.mark.parametrize("module_name", CHECKED_MODULES, ids=str)
def test_documented_examples_hold(module_name: str) -> None:
    """Every doctest in the module runs and matches its stated output."""
    outcome = run_examples(module_name)

    assert outcome.held, f"{module_name}: {outcome.verdict} - {outcome.detail}"


@pytest.mark.parametrize("module_name", sorted(NOT_IMPORTABLE_HERE), ids=str)
def test_a_module_listed_as_unimportable_still_is(module_name: str) -> None:
    """This list shrinks too, and for the same reason the other one does.

    A module that has been given a package-relative import now works
    here, and keeping its exemption would leave its examples unrun with
    nothing saying so. Failing here is good news: move the entry out,
    or delete it if the examples hold.
    """
    assert module_name in GATE_MODULES, (
        f"{module_name} is exempted but no longer discovered; remove it"
    )

    outcome = run_examples(module_name)

    assert outcome.verdict is Verdict.NOT_IMPORTABLE, (
        f"{module_name} imports here now ({outcome.detail}). Remove it from "
        "NOT_IMPORTABLE_HERE; if its examples are stale, that belongs in "
        "KNOWN_STALE_EXAMPLES instead."
    )


def test_the_two_exemption_lists_do_not_overlap() -> None:
    """A module is exempted for one reason or the other, never both.

    An entry in both would be retired by neither: whichever list was
    edited first, the other would keep it out of `CHECKED_MODULES`.
    """
    both = sorted(KNOWN_STALE_EXAMPLES & NOT_IMPORTABLE_HERE)

    assert not both, f"exempted twice, so retiring either changes nothing: {both}"


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
