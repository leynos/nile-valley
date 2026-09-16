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

import contextlib
import doctest
import enum
import importlib
import os
import re
import stat
import sys
import tempfile
import typing as typ
from collections.abc import Iterator
from pathlib import Path

import pytest

#: `conftest.py` is pytest's to import. Importing it a second time under
#: a dotted name would run its `sys.path` setup again against a
#: different module object, so its own examples are left to pytest.
NOT_OURS_TO_IMPORT = frozenset({"conftest", "__init__"})

#: Directories under `scripts` this gate does not import, for the same
#: reason as `conftest`: the suite is pytest's, and a second import
#: under a dotted name re-runs every module-level statement against a
#: different module object. It is also not merely untidy. The spelling
#: gate runs a narrower pytest invocation that omits `cmd-mox` on
#: purpose, and three modules here import it at module level, so under
#: that invocation the second import raises and this gate reports a
#: missing package as a stale example.
#:
#: Their own examples are not abandoned: executing them is
#: `--doctest-modules` on the suite's own invocation, which is where a
#: module pytest already imports belongs.
NOT_OURS_TO_WALK = frozenset({"tests"})

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
        and NOT_OURS_TO_WALK.isdisjoint(path.relative_to(PACKAGE_ROOT).parts[:-1])
    ]
    assert names, f"no modules found under {PACKAGE_ROOT}; the walk is wrong"
    return tuple(names)


GATE_MODULES = _module_names()

#: Modules whose examples did not hold when the walk replaced the hand
#: list, on 2026-09-15. Fourteen modules, down from seventeen: the
#: manifest writer's examples named absolute paths under `/tmp` and
#: wrote to them, so running them at all was the defect and repairing
#: them retired its entry the same day. The platform renderer went the
#: same way: its examples called out to OpenTofu and wrote a variables
#: file under the temporary directory they named, behind a comment
#: saying they were illustrative, which `doctest` does not read. They
#: are marked as skipped now, which is a thing it does read, and they
#: hold. The input preparer went with them: its two examples were
#: repaired to make their own temporary directory, and once they ran at
#: all the only thing still wrong was that they did not state the
#: secret masking the call prints. The rest mostly name functions
#: that have since been renamed or removed. Repairing those is not this
#: branch's work, and turning the gate red on it would be worse than
#: recording it.
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
    "scripts._infra_k8s_tofu",
    "scripts._prepare_infra_k8s_models",
    "scripts._provision_cluster_flow",
    "scripts._render_platform_inputs",
    "scripts._vault_bootstrap",
    "scripts._vault_commands",
    "scripts.check_test_dependencies",
    "scripts.publish_infra_k8s_outputs",
    }
)

#: Modules this gate cannot import, for a reason that is not a stale
#: example and does not belong beside one. Each imports a sibling by
#: bare name, which resolves only when `scripts` is itself on the path.
#: The spelling gate runs that way and they work there; under this
#: suite's layout they are `scripts.<name>` and the bare import misses.
#:
#: Recorded separately because the distinction is the point. Collapsing
#: an import failure into "stale examples" is what let an exemption for
#: a deleted module satisfy the shrink-only rule forever, and it would
#: equally hide three modules whose examples have never run at all.
#: Adding `scripts` to `sys.path` here would import each of them twice
#: under two names, which is the fault this gate was just scoped to
#: avoid, so the fix belongs in the modules. Tracked with the stale
#: examples in leynos/nile-valley#103.
NOT_IMPORTABLE_HERE = frozenset(
    {
        "scripts.generate_typos_config",
        "scripts.typos_rollout",
        "scripts.typos_rollout_http",
    }
)

CHECKED_MODULES = tuple(
    m
    for m in GATE_MODULES
    if m not in KNOWN_STALE_EXAMPLES and m not in NOT_IMPORTABLE_HERE
)


class Verdict(enum.StrEnum):
    """How a module's examples came out.

    Three things go wrong here and only one of them is a wrong expected
    value. Collapsing them into "a reason" made the exemption test
    unfalsifiable: a module that had been deleted failed to import, an
    import failure read as a reason, and a reason was all the test
    asked for. They are separate states now because the test has to
    tell them apart.
    """

    HELD = "held"
    NOT_IMPORTABLE = "not-importable"
    STALE = "stale"


class Outcome(typ.NamedTuple):
    """What running one module's examples produced.

    Attributes
    ----------
    verdict:
        Which of the three states it reached.
    detail:
        A short human-readable account, for the assertion message.
    """

    verdict: Verdict
    detail: str

    @property
    def held(self) -> bool:
        """Whether every example held."""
        return self.verdict is Verdict.HELD


@contextlib.contextmanager
def _in_a_scratch_directory() -> Iterator[Path]:
    """Run the body with the process rooted in a fresh temporary directory.

    Documented examples are ordinary code and some of them write. Two
    in the manifest writer named absolute paths under `/tmp` and
    created them on every run of this suite, on a machine the gate
    shares with everything else. Those two are repaired at the source,
    but a gate that walks every module cannot assume the next one added
    will be careful, so the execution happens somewhere disposable and
    the process is put back afterwards.

    Yields
    ------
    Path
        The scratch directory, already the working directory.
    """
    origin = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="doctest-gate-") as directory:
        scratch = Path(directory)
        os.chdir(scratch)
        try:
            yield scratch
        finally:
            os.chdir(origin)


def run_examples(module_name: str) -> Outcome:
    """Import a module and run its documented examples, in isolation.

    The explicit boundary. This is the only function here that imports
    anything, executes anything or touches a filesystem, and it does
    the last of those from a scratch directory it throws away. Its
    callers read an `Outcome` and decide; they cause nothing.

    Parameters
    ----------
    module_name : str
        The dotted module name.

    Returns
    -------
    Outcome
        The verdict and a short account of it.
    """
    # The import is inside the boundary, not before it. A first import
    # runs the module's top-level statements, and a module that writes
    # at import time would otherwise do so in the repository: the walk
    # derives names from files and does not pre-import them, so for most
    # of these this call is the first import there has been.
    with _in_a_scratch_directory():
        try:
            module = importlib.import_module(module_name)
        except Exception as error:  # noqa: BLE001 - the reason is the answer
            return Outcome(Verdict.NOT_IMPORTABLE, f"{type(error).__name__}: {error}")
        try:
            results = doctest.testmod(
                module, verbose=False, optionflags=doctest.NORMALIZE_WHITESPACE
            )
        except Exception as error:  # noqa: BLE001 - a malformed docstring lands here
            return Outcome(Verdict.STALE, f"{type(error).__name__}: {error}")
    if results.failed:
        return Outcome(
            Verdict.STALE, f"{results.failed} of {results.attempted} example(s) stale"
        )
    return Outcome(Verdict.HELD, f"{results.attempted} example(s) held")


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


#: Directories every process on the machine shares. An example that
#: names one of these as somewhere to write cannot be watched: their
#: contents change constantly for unrelated reasons, so a gate that
#: compared them would fail on another process's file. They are refused
#: instead of watched.
SHARED_ROOTS = frozenset(
    {
        Path(tempfile.gettempdir()),
        Path("/tmp"),  # noqa: S108 - named to be refused, never written to
        Path("/var/tmp"),  # noqa: S108 - as above
    }
)

#: A quoted absolute filesystem path appearing in an example. A URL is
#: quoted and contains a slash too, so a scheme-relative `//` is
#: excluded rather than the leading slash being taken as proof.
_ABSOLUTE_IN_AN_EXAMPLE = re.compile(r"""["'](/[^"'\s]*)["']""")


def _absolute_literals_in(module_name: str) -> list[str]:
    """Return the absolute path literals one module's examples mention.

    Reads the source rather than running it: both callers need the list
    before anything is executed, one to watch those paths and one to
    refuse some of them outright.

    Parameters
    ----------
    module_name : str
        The dotted module name.

    Returns
    -------
    list[str]
        The literals, in the order they appear.
    """
    path = REPOSITORY_ROOT / Path(*module_name.split(".")).with_suffix(".py")
    return absolute_literals_in_source(path.read_text(encoding="utf-8"))


def absolute_literals_in_source(source: str) -> list[str]:
    """Return the absolute path literals the examples in ``source`` mention.

    Split from the module reader so the rule can be exercised against a
    source written for the purpose. Parametrised over the repository's
    own modules it can only fail on a regression, which means a mutation
    that removes it survives, which means nothing shows the rule works.

    Parameters
    ----------
    source : str
        Python source.

    Returns
    -------
    list[str]
        The literals, in the order they appear.
    """
    found: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith((">>> ", "... ")):
            continue
        # A commented example is inert text; `doctest` never runs it.
        if stripped[4:].lstrip().startswith("#"):
            continue
        found.extend(
            literal
            for literal in _ABSOLUTE_IN_AN_EXAMPLE.findall(stripped)
            if not literal.startswith("//")
        )
    return found


def shared_roots_named_in_source(source: str) -> list[str]:
    """Return the shared temporary roots the examples in ``source`` name.

    One place, called by the rule over the repository's modules and by
    the test that drives it with a source written to violate it. Keeping
    the membership test here is what lets the second prove the first:
    with it inlined in the rule, nothing exercised it, because no module
    in the repository names one.

    Parameters
    ----------
    source : str
        Python source.

    Returns
    -------
    list[str]
        The offending literals, in the order they appear.
    """
    return [
        literal
        for literal in absolute_literals_in_source(source)
        if Path(literal) in SHARED_ROOTS
    ]


def _absolute_paths_named_in_examples() -> tuple[Path, ...]:
    """Return every absolute path the discovered examples mention.

    Reads the source rather than running it, because this is the list a
    later assertion watches while the examples run.

    Most of these are inert: a path handed to a value object that
    nothing writes is named but never touched, which is why naming one
    is not itself the offence. What matters is which of them exist
    afterwards.

    Returns
    -------
    tuple[Path, ...]
        The paths, deduplicated, in a stable order.
    """
    found: set[str] = set()
    for module_name in GATE_MODULES:
        found.update(_absolute_literals_in(module_name))
    return tuple(Path(name) for name in sorted(found))


def _signature(path: Path) -> object | None:
    """Return a value that changes if ``path`` is created or written.

    Existence alone is not enough. This gate first ran green on a host
    where an earlier run had already made the files, so the run that
    made them again looked like it had made nothing; the same check
    failed on CI's clean machine. History must not be able to mask the
    run.

    A directory is compared by existence only. The ones named here are
    shared, `/tmp` among them, and their modification time moves
    whenever anything else on the machine touches them.

    Parameters
    ----------
    path : Path
        The path to read.

    Returns
    -------
    object or None
        None when absent, a marker for a directory, and the size and
        modification time for a file.
    """
    try:
        status = path.stat()
    except OSError:
        return None
    if stat.S_ISDIR(status.st_mode):
        if path in SHARED_ROOTS:
            # Compared by existence alone. These are shared with every
            # other process on the machine, so their contents and their
            # modification time move for reasons that have nothing to do
            # with this run, and watching them would make the gate
            # flaky, which is worse than the gap.
            #
            # The gap is real: a write to a path derived beneath one of
            # these, rather than named outright, is invisible here.
            # `test_no_example_names_a_shared_temporary_root` is what
            # closes it, by refusing the only way an example can reach
            # one.
            return "a shared directory"
        # Named and not shared, so its contents are this run's business.
        # An example that writes a derived file beneath a directory it
        # named is caught here rather than by its own name.
        return sorted(str(child.relative_to(path)) for child in path.rglob("*"))
    return (status.st_size, status.st_mtime_ns)


@pytest.mark.parametrize("module_name", GATE_MODULES, ids=str)
def test_no_example_names_a_shared_temporary_root(module_name: str) -> None:
    """No example may hand a shared temporary directory to anything.

    This is the one gap the host-write check cannot close by watching.
    A shared root is compared by existence, because its contents move
    for reasons unrelated to this run, so a file written to a path
    derived beneath one is invisible: an example passing
    ``runner_temp=Path("/tmp")`` had the code beneath it create
    ``/tmp/render-manifests/platform.tfvars.json`` on every run of this
    suite, and the watch said nothing.

    Refusing the root closes it, because a derived path can only escape
    into a directory the example named. The remedy is the same as
    everywhere else here: make a temporary directory, and then the
    example can also assert what it produced.
    """
    path = REPOSITORY_ROOT / Path(*module_name.split(".")).with_suffix(".py")
    named = set(shared_roots_named_in_source(path.read_text(encoding="utf-8")))

    assert not named, (
        f"{module_name} hands a shared temporary directory to an example: "
        f"{sorted(str(path) for path in named)}. Anything written beneath it "
        "cannot be watched. Use a tempfile.TemporaryDirectory instead."
    )


def test_running_every_example_creates_nothing_on_the_host() -> None:
    """Executing the examples leaves the paths they name as it found them.

    This is the half of the write boundary that isolation cannot
    provide. Running from a temporary directory contains a relative
    write and contains nothing at all about an absolute one: two
    examples here named `/tmp/vars.tfvars.json` and `/tmp/out` and
    created them on every run of this suite, on a machine the gate
    shares with everything else. No sandbox available to a test can
    stop that, so what the run creates is watched instead.

    Naming an absolute path is not the offence, which is why this
    watches the paths rather than the mentions. Most of those named
    here are handed to a value object that nothing writes, and they
    stay absent whatever the example does with them.
    """
    watched = _absolute_paths_named_in_examples()
    assert watched, "no example names an absolute path; this now asserts nothing"
    before = {path: _signature(path) for path in watched}

    for module_name in (*CHECKED_MODULES, *sorted(KNOWN_STALE_EXAMPLES)):
        run_examples(module_name)

    touched = sorted(str(path) for path in watched if _signature(path) != before[path])

    assert not touched, (
        f"running the examples wrote {touched} on the host. An example that "
        "needs a file should make its own tempfile.TemporaryDirectory, which "
        "also lets it assert what it produced instead of asserting nothing."
    )


#: What the disposable-directory test's purpose-built example writes.
#: Named once because the test both creates it and looks for it in two
#: places, and a disagreement between those spellings would make the
#: test pass by looking for the wrong thing.
WITNESS = "left-behind-by-an-example"


def test_the_examples_are_run_from_somewhere_disposable(tmp_path: Path) -> None:
    """`run_examples` executes its examples outside the repository.

    Asserted through `run_examples` rather than through the context
    manager it uses, because removing the isolation from `run_examples`
    while leaving the helper intact is a one-line edit that a test of
    the helper alone would not notice.

    A module is written for the purpose: its example writes a relative
    file, so where that file lands is where the examples ran.

    The landing sites are cleared first. Proving this by mutation means
    deliberately running the gate without its isolation, which leaves
    the very file this looks for; without the clearing, the next honest
    run then fails on the last dishonest one's litter and says the
    isolation is broken when it is not.
    """
    landings = (REPOSITORY_ROOT / WITNESS, tmp_path / WITNESS)
    for landing in landings:
        landing.unlink(missing_ok=True)

    module = tmp_path / "writes_relatively.py"
    module.write_text(
        '"""A module whose example writes beside the working directory.\n\n'
        "Examples\n--------\n"
        ">>> from pathlib import Path\n"
        f'>>> Path("{WITNESS}").write_text("x", encoding="utf-8")\n'
        "1\n"
        '"""\n',
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        outcome = run_examples("writes_relatively")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("writes_relatively", None)

    assert outcome.held, outcome.detail
    assert not (REPOSITORY_ROOT / WITNESS).exists(), (
        "the examples ran in the repository root"
    )
    assert not (tmp_path / WITNESS).exists(), (
        "the examples ran in the module's own directory"
    )


def test_running_the_examples_leaves_the_working_directory_alone() -> None:
    """The gate puts the process back where it found it.

    The isolation is a `chdir`, and a `chdir` that is not undone moves
    every test that runs after this one.
    """
    before = Path.cwd()

    for module_name in sorted(KNOWN_STALE_EXAMPLES)[:3]:
        run_examples(module_name)

    assert Path.cwd() == before, f"the gate left the process in {Path.cwd()}"


def test_an_example_that_writes_relatively_leaves_no_trace() -> None:
    """A write from an example lands in the scratch directory, not here.

    Two examples in the manifest writer named absolute paths under
    `/tmp` and created them on every run of this suite. Those are
    repaired at the source, but the next careless example is not
    hypothetical, so the isolation is asserted rather than trusted.
    """
    before = sorted(REPOSITORY_ROOT.iterdir())

    with _in_a_scratch_directory() as scratch:
        Path("written-by-an-example").write_text("x", encoding="utf-8")
        assert (scratch / "written-by-an-example").exists(), (
            "the scratch directory is not where a relative write landed"
        )

    assert sorted(REPOSITORY_ROOT.iterdir()) == before, (
        "running the examples added something to the repository root"
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


class TestTheRulesBiteOnSomethingWrittenToBreakThem:
    """Each guard is shown working, not merely shown passing.

    Parametrised over the repository's own modules, every rule here
    passes because the sources are correct, so removing the rule changes
    nothing and a mutation of it survives. These drive the mechanisms
    directly against inputs written to violate them.
    """

    def test_the_shared_root_rule_sees_one_when_there_is_one(self) -> None:
        """A source naming a shared temporary root is detected."""
        source = '\'\'\'Doc.\n\n>>> render(runner_temp=Path("/tmp"))\n\'\'\'\n'

        named = shared_roots_named_in_source(source)

        assert named == ["/tmp"], named

    def test_a_commented_example_is_not_counted(self) -> None:
        """`doctest` never runs a commented line, so nor does the rule.

        The other half of the rule: it must not fire on text that
        cannot execute, or it would force changes to examples that were
        never going to write anything.
        """
        source = '\'\'\'Doc.\n\n>>> # render(runner_temp=Path("/tmp"))\n\'\'\'\n'

        assert absolute_literals_in_source(source) == []

    def test_a_named_directory_that_gains_a_child_is_seen(
        self, tmp_path: Path
    ) -> None:
        """A write beneath a watched directory changes its signature.

        This is the hole the review found: a file created at a path
        derived beneath a directory an example named, rather than at the
        name itself. Comparing the directory by existence missed it.
        """
        watched = tmp_path / "output"
        watched.mkdir()
        before = _signature(watched)

        (watched / "derived").mkdir()
        (watched / "derived" / "written.json").write_text("{}", encoding="utf-8")

        assert _signature(watched) != before, (
            "a file written beneath a watched directory left its signature "
            "unchanged, so the host-write check would not see it"
        )

    def test_a_shared_directory_is_not_watched_that_way(self) -> None:
        """A shared root is compared by existence, deliberately.

        Its contents move for reasons unrelated to this run, so watching
        them would make the gate fail on another process's file. The
        compensating control is that an example may not name one at all.
        """
        assert _signature(Path(tempfile.gettempdir())) == "a shared directory"

    def test_the_examples_are_imported_inside_the_scratch_directory(
        self, tmp_path: Path
    ) -> None:
        """A module that writes at import time writes into the scratch.

        The walk derives names from files and does not pre-import them,
        so `run_examples` performs the first import for most modules,
        and a module-level statement runs then rather than inside any
        example. Importing before entering the boundary put that write
        in the repository.
        """
        witness = "written-while-importing"
        module = tmp_path / "writes_on_import.py"
        module.write_text(
            '"""A module that writes as it is imported."""\n\n'
            "from pathlib import Path\n\n"
            f'Path("{witness}").write_text("x", encoding="utf-8")\n',
            encoding="utf-8",
        )
        for landing in (REPOSITORY_ROOT / witness, tmp_path / witness):
            landing.unlink(missing_ok=True)
        sys.path.insert(0, str(tmp_path))
        try:
            outcome = run_examples("writes_on_import")
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("writes_on_import", None)

        assert outcome.verdict is not Verdict.NOT_IMPORTABLE, outcome.detail
        assert not (REPOSITORY_ROOT / witness).exists(), (
            "the module was imported in the repository root"
        )
        assert not (tmp_path / witness).exists(), (
            "the module was imported in its own directory"
        )
