"""Contract tests for the repository's CodeScene rule overrides.

`.codescene/code-health-rules.json` sat here in a shape CodeScene does not
accept, so the exemption it declared never applied. Nothing caught it: the
file is valid JSON, the tool's own diagnostic blames JSON syntax, and the
warning goes to a log nobody reads. CodeScene's verdicts simply carried on
without the override.

The rule set was dead as well as unreadable. Its glob was `**/domain/*.rs`
and this repository contains no Rust, so it was removed rather than repaired.
These tests guard the file a future exemption would be written into: they
assert the documented schema rather than merely that the file parses, require
each exemption to justify itself, and require each glob to still match
something, because a glob left behind by a rename or a copy is an exemption
that quietly stops applying.

`cs rules-config validate` is the local check the developers' guide points at.
The command-line tool does not belong in CI, because the GitHub integration
reads the same rule set; these tests are a schema check rather than a stand-in
for either.
"""

from __future__ import annotations

import collections.abc as cabc
import json
import typing as typ
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPOSITORY_ROOT / ".codescene" / "code-health-rules.json"


class RuleRecord(typ.TypedDict):
    """One rule override: a prose name and a weight between 0.0 and 1.0."""

    name: str
    weight: float


class ThresholdRecord(typ.TypedDict):
    """One threshold override: a name and the value to use instead.

    An array entry rather than a mapping key, which is the shape
    `cs docs code-health-rules-template` prints. The distinction is not
    cosmetic: given a mapping here the CodeScene CLI does not report a
    schema problem, it terminates with an unhandled exception and asks
    for the stack trace to be sent to support.
    """

    name: str
    value: float


class RuleSetRecord(typ.TypedDict, total=False):
    """One rule set, as `cs docs code-health-rules-template` emits it."""

    matching_content_path: str
    matching_content_path_doc: str
    content_filter: str
    rules: list[RuleRecord]
    thresholds: list[ThresholdRecord]


class RulesDocument(typ.TypedDict, total=False):
    """The rule file as a whole."""

    usage: str
    rule_sets: list[RuleSetRecord]


#: Keys `cs docs code-health-rules-template` emits for a rule set. `usage` and
#: the `_doc` suffixes are documentation the template carries itself, so they
#: are allowed rather than required.
RULE_SET_KEYS = frozenset(
    {
        "matching_content_path",
        "matching_content_path_doc",
        "content_filter",
        "rules",
        "thresholds",
    }
)

MINIMUM_JUSTIFICATION = 80

#: The type each rule-set field must have when it is present. Checking
#: this before anything reads a field is what stops a wrong type from
#: passing as an absence: `"rules": ""` iterates zero times and so
#: satisfies every rule check, and a list of 81 strings has a length
#: above the justification minimum without being prose at all. Either
#: one alone would sail through with a glob that matches.
RULE_SET_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "matching_content_path": str,
    "matching_content_path_doc": str,
    "content_filter": str,
    "rules": list,
    "thresholds": list,
}

#: The template's placeholder for a threshold nobody has set. It leaves
#: the default in place, so a rule set still carrying one is template
#: residue rather than an override: the file's own usage text says to
#: keep the rules you want and remove the rest.
UNSET_THRESHOLD = "-"


class RuleSets(typ.NamedTuple):
    """A parsed rule document and the tree its globs resolve against.

    The checks take this rather than reaching for `RULES_PATH`
    themselves. Reading a file and parsing JSON behind a zero-argument
    call made every check fallible for reasons that had nothing to do
    with the rule it states, and made the tests patch a module global to
    say anything at all. With the document passed in, each check is a
    function of its argument, and the one that resolves globs takes the
    tree it resolves them against instead of assuming the repository.

    Attributes
    ----------
    document : RulesDocument or dict
        The parsed rule file.
    root : Path
        The tree `matching_content_path` patterns are resolved against.
    """

    document: RulesDocument | dict[str, object]
    root: Path


def read_rules(
    path: Path | None = None, *, root: Path = REPOSITORY_ROOT
) -> RuleSets:
    """Read and parse one rule file, and do nothing else with it.

    The only filesystem access in this module's checking path, kept
    apart from them so that none of them has to be driven through a
    patched global to be exercised.

    Parameters
    ----------
    path : Path, optional
        The file to read. Defaults to the committed rule file.
    root : Path
        The tree globs are resolved against.

    Returns
    -------
    RuleSets
        The parsed document and its root.

    Raises
    ------
    AssertionError
        If the file does not hold a JSON object.
    """
    source = RULES_PATH if path is None else path
    document = json.loads(source.read_text(encoding="utf-8"))
    assert isinstance(document, dict), (
        f"the rule file must be a JSON object: {source}"
    )
    return RuleSets(document=document, root=root)


def _rule_sets(subject: RuleSets) -> list[RuleSetRecord]:
    """Return the document's rule sets, failing if the shape is wrong.

    Parameters
    ----------
    subject : RuleSets
        The document to read.

    Returns
    -------
    list[RuleSetRecord]
        The rule sets.
    """
    document = subject.document
    assert isinstance(document, dict), "the rule file must be a JSON object"
    rule_sets = document.get("rule_sets")
    assert isinstance(rule_sets, list), (
        "the rule file must carry a top-level 'rule_sets' array; a top-level "
        "'rules' object is the shape CodeScene rejects, and it rejects it "
        "with a message about JSON syntax that sends the reader elsewhere"
    )
    assert rule_sets, "an empty rule_sets array declares no override at all"
    for rule_set in rule_sets:
        assert isinstance(rule_set, dict), "each rule set must be an object"
    return typ.cast("list[RuleSetRecord]", rule_sets)


def _check_rule(rule: RuleRecord | dict[str, object]) -> None:
    """Assert one rule override carries a prose name and a weight.

    Parameters
    ----------
    rule : RuleRecord or dict
        One entry of a rule set's ``rules`` array. That is a rule
        override, not a rule set: only `RuleRecord` declares `name` and
        `weight`, so only it makes the two reads below well typed.
    """
    assert set(rule) == {"name", "weight"}, (
        f"a rule override carries exactly a name and a weight: {rule}"
    )
    name = rule["name"]
    assert isinstance(name, str) and " " in name, (
        "rules are named in prose, as in 'String Heavy Function Arguments', "
        f"not as a hyphenated slug: {name!r}"
    )
    weight = rule["weight"]
    # A Boolean passes `isinstance(..., int)` and falls inside the range, but
    # CodeScene expects a number, so the contract would approve a file the
    # authoritative validator rejects.
    assert not isinstance(weight, bool), (
        f"a rule's weight is a number, not a Boolean: {weight!r}"
    )
    assert isinstance(weight, int | float) and 0.0 <= weight <= 1.0, (
        "a rule's weight is a relative multiplier between 0.0 and 1.0, not a "
        f"threshold: {weight!r}"
    )


def check_schema(subject: RuleSets) -> None:
    """Assert the rule file uses the keys CodeScene reads.

    Asserting the key names matters more than it looks. The shape this
    replaces used hyphenated keys, which CodeScene's parser reads as
    namespaced keywords and refuses, so a typo here fails the same way:
    silently, with the override ignored.

    Parameters
    ----------
    subject : RuleSets
        The document to check.
    """
    for rule_set in _rule_sets(subject):
        assert isinstance(rule_set, dict), "each rule set must be an object"
        unexpected = set(rule_set) - RULE_SET_KEYS
        assert not unexpected, (
            f"unrecognized rule set keys {sorted(unexpected)}; CodeScene "
            "ignores what it does not recognize"
        )
        _check_field_types(rule_set)
        for rule in rule_set.get("rules", []):
            _check_rule(rule)
        for threshold in rule_set.get("thresholds", []):
            _check_threshold(threshold)


def _check_threshold(threshold: ThresholdRecord | dict[str, object]) -> None:
    """Assert one threshold override names a rule and a positive number.

    The bounds come from the tool rather than from taste. CodeScene
    rejects an entry whose value is absent, zero, negative or
    non-numeric with "Make sure all thresholds are positive integers",
    and it accepts a fractional one, so positive is the rule and integer
    is not.

    Parameters
    ----------
    threshold : ThresholdRecord or dict
        The threshold entry to check.
    """
    assert isinstance(threshold, dict), (
        f"each threshold override is an object, not a bare value: {threshold!r}"
    )
    assert set(threshold) == {"name", "value"}, (
        f"a threshold override carries exactly a name and a value: {threshold}"
    )
    name = threshold["name"]
    assert isinstance(name, str) and name, (
        f"a threshold names the code-health measure it overrides: {name!r}"
    )
    value = threshold["value"]
    assert value != UNSET_THRESHOLD, (
        f"{name} still carries the template's {UNSET_THRESHOLD!r} placeholder, "
        "which overrides nothing; set the value or remove the entry"
    )
    # A Boolean is an int and would fall inside the bound, as it would
    # for a rule's weight.
    assert not isinstance(value, bool), (
        f"a threshold's value is a number, not a Boolean: {value!r}"
    )
    assert isinstance(value, int | float), (
        "a threshold's value is a number. CodeScene coerces a numeric string "
        "rather than refusing it, so a quoted value is accepted today and is "
        f"a difference between the file and its schema that nothing reports: "
        f"{value!r}"
    )
    assert value > 0, (
        "CodeScene refuses a value that is not positive, naming the whole "
        f"file rather than this entry: {value!r}"
    )


def _check_field_types(rule_set: RuleSetRecord | dict[str, object]) -> None:
    """Assert every field a rule set declares has its documented type.

    Checked before anything reads a field, because a wrong type does not
    announce itself downstream: it reads as an absence. A ``rules`` value
    of ``""`` iterates zero times and so satisfies every rule check, and
    a ``matching_content_path_doc`` of eighty-one list items is longer
    than the justification minimum without being prose. A rule set
    carrying both, over a glob that matches, passed every check here
    while violating the schema twice.

    Parameters
    ----------
    rule_set : RuleSetRecord or dict
        The rule set to check.
    """
    # Read through a plain mapping. The field names come from
    # RULE_SET_FIELD_TYPES at runtime, and a TypedDict may only be
    # indexed by a literal, so the alternative is a suppression that
    # Pyright reads as covering the whole line and every future
    # diagnostic on it.
    fields = typ.cast("dict[str, object]", rule_set)
    for field, expected in RULE_SET_FIELD_TYPES.items():
        if field not in fields:
            continue
        value = fields[field]
        # A Boolean is an int, so the same trap as a rule's weight
        # applies to any field whose type is not bool.
        assert not isinstance(value, bool), (
            f"{field} is a {expected}, not a Boolean: {value!r}"
        )
        assert isinstance(value, expected), (
            f"{field} must be a {getattr(expected, '__name__', expected)}; "
            f"a wrong type here reads downstream as an absence rather than "
            f"as an error: {value!r}"
        )


def check_justifications(subject: RuleSets) -> None:
    """Assert each rule set explains itself, so a reader can judge it.

    An exemption without a stated reason is indistinguishable from one nobody
    revisited, which is how a narrow allowance becomes a permanent blind spot.

    Parameters
    ----------
    subject : RuleSets
        The document to check.
    """
    for rule_set in _rule_sets(subject):
        justification = rule_set.get("matching_content_path_doc", "")
        assert isinstance(justification, str), (
            "matching_content_path_doc is prose; a list of eighty-one items "
            f"is long without saying anything: {justification!r}"
        )
        assert len(justification) > MINIMUM_JUSTIFICATION, (
            "each rule set needs a matching_content_path_doc saying why the "
            f"exemption is deliberate: {rule_set.get('matching_content_path')!r}"
        )


def check_globs_match(subject: RuleSets) -> None:
    """Assert each rule set's glob matches at least one file.

    A path left behind by a rename, or copied from another repository, leaves
    an exemption that quietly stops applying. That was half of this file's
    defect: its glob named Rust sources in a repository that has none.

    The tree is `subject.root` rather than `REPOSITORY_ROOT`, so a test
    can ask what this check says about a directory it controls.

    Parameters
    ----------
    subject : RuleSets
        The document to check, and the tree to resolve globs against.
    """
    for rule_set in _rule_sets(subject):
        pattern = rule_set.get("matching_content_path")
        assert isinstance(pattern, str) and pattern, (
            "each rule set must declare a matching_content_path"
        )
        matched = next(
            (path for path in subject.root.glob(pattern) if path.is_file()),
            None,
        )
        assert matched is not None, (
            f"no file matches {pattern!r}; an exemption that matches nothing "
            "is either stale or was never right. A pattern resolving only to "
            "a directory counts as nothing, because CodeScene weighs files"
        )


#: Every check, as a function of the document it checks. The uniform
#: signature is what lets the tests below drive all three from one
#: parametrisation.
Check: typ.TypeAlias = cabc.Callable[[RuleSets], None]
CHECKS: tuple[Check, ...] = (check_schema, check_justifications, check_globs_match)


#: One rule file in the documented shape, shared by the driver that
#: checks a document directly and the one that reads it from disk, so
#: the two cannot disagree about what "well formed" means.
A_VALID_DOCUMENT: dict[str, object] = {
    "usage": "Repo-scoped CodeScene overrides.",
    "rule_sets": [
        {
            "matching_content_path": "scripts/*.py",
            "matching_content_path_doc": (
                "A justification long enough to say why the exemption is "
                "deliberate, what it covers, and when to reassess it."
            ),
            "rules": [{"name": "String Heavy Function Arguments", "weight": 0.0}],
        }
    ],
}


class TestTheReadBoundary:
    """`read_rules` does one job: turn a file into a `RuleSets`.

    It is the only part of this module that touches the filesystem, so
    it is the only part that needs a file to exercise it. Separating it
    is what let every check above become a function of its argument.
    """

    def test_a_representative_valid_file_is_read_and_passes_every_check(
        self, tmp_path: Path
    ) -> None:
        """A well-formed rule file on disk reaches the checks intact.

        End to end over the boundary: written as JSON, read back, and
        put through all three checks. A parse that dropped or reshaped
        a field would pass the pure tests above and fail here.
        """
        path = tmp_path / "code-health-rules.json"
        path.write_text(json.dumps(A_VALID_DOCUMENT), encoding="utf-8")

        subject = read_rules(path)

        assert subject.root == REPOSITORY_ROOT, "the default root is the repository"
        for check in CHECKS:
            check(subject)

    def test_a_representative_invalid_file_is_read_and_fails_its_check(
        self, tmp_path: Path
    ) -> None:
        """A rule file whose glob matches nothing fails, read from disk.

        The invalid half of the pair, so the boundary is shown to carry
        a rejection through and not only an acceptance.
        """
        document = {
            "usage": "Repo-scoped CodeScene overrides.",
            "rule_sets": [
                {
                    "matching_content_path": "**/domain/*.rs",
                    "matching_content_path_doc": "x" * 200,
                    "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                }
            ],
        }
        path = tmp_path / "code-health-rules.json"
        path.write_text(json.dumps(document), encoding="utf-8")

        with pytest.raises(AssertionError, match="no file matches"):
            check_globs_match(read_rules(path))

    def test_a_file_holding_something_other_than_an_object_is_refused(
        self, tmp_path: Path
    ) -> None:
        """A JSON array parses, and is still not a rule file.

        The read is where this belongs: a check taking the document can
        assume it was given one, and saying so here names the file.
        """
        path = tmp_path / "code-health-rules.json"
        path.write_text(json.dumps(["rule_sets"]), encoding="utf-8")

        with pytest.raises(AssertionError, match="must be a JSON object"):
            read_rules(path)


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.__name__)
def test_any_committed_rule_file_passes_each_check(check: Check) -> None:
    """The committed rule file, if there is one, satisfies every check.

    There is none today: the only rule set was dead as well as unreadable,
    and removing it changed no verdict because CodeScene never read the file.
    So this skips rather than asserting the absence.

    Asserting the absence was the wrong shape. It made re-adding a rule file
    fail a test whose message said to delete it, and a deleted test validates
    nothing: every other test here patches `RULES_PATH` to a temporary file,
    so a malformed committed `.codescene/code-health-rules.json` would have
    received no schema, justification or glob check at all. Skipping while the
    file is absent means the checks arrive with the file rather than after
    someone remembers to reinstate them.
    """
    if not RULES_PATH.exists():
        pytest.skip(f"{RULES_PATH.name} is absent, so there is nothing to check")
    check(read_rules())


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.__name__)
def test_a_rule_file_would_have_to_pass_each_check(check: Check) -> None:
    """A well-formed rule document satisfies every check.

    The document is built here rather than committed, so the checks stay
    exercised while the repository declares no overrides. It is passed
    in rather than written to a file and reached through a patched
    global, which is what taking the document as an argument bought.
    """
    check(RuleSets(document=A_VALID_DOCUMENT, root=REPOSITORY_ROOT))


@pytest.mark.parametrize(
    ("document", "failing_checks"),
    [
        pytest.param(
            {
                "rules": {
                    "string-heavy-function-arguments": {
                        "threshold-by-pattern": {"**/domain/*.rs": 100}
                    }
                }
            },
            CHECKS,
            id="the-file-this-replaces",
        ),
        pytest.param(
            {"rule_sets": [{"rules": [{"name": "String Heavy", "weight": 100}]}]},
            CHECKS,
            id="a-threshold-where-a-weight-belongs",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "string-heavy-arguments", "weight": 0.0}],
                    }
                ]
            },
            (check_schema,),
            id="a-slug-where-a-prose-name-belongs",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "**/domain/*.rs",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                    }
                ]
            },
            (check_globs_match,),
            id="a-glob-matching-nothing",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                    }
                ]
            },
            (check_justifications,),
            id="an-unjustified-exemption",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                    }
                ]
            },
            (check_globs_match,),
            id="a-glob-matching-only-a-directory",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": True}],
                    }
                ]
            },
            (check_schema,),
            id="a-boolean-weight-true",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": False}],
                    }
                ]
            },
            (check_schema,),
            id="a-boolean-weight-false",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": ["x"] * 81,
                        "rules": "",
                    }
                ]
            },
            (check_schema, check_justifications),
            id="wrong-types-that-read-as-absences",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                        "thresholds": {"function_lines_of_code_warning": 100},
                    }
                ]
            },
            (check_schema,),
            id="thresholds-as-a-mapping",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                        "thresholds": [
                            {"name": "function_lines_of_code_warning", "value": "100"}
                        ],
                    }
                ]
            },
            (check_schema,),
            id="a-threshold-value-that-is-a-string",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                        "thresholds": [
                            {"name": "function_lines_of_code_warning", "value": 0}
                        ],
                    }
                ]
            },
            (check_schema,),
            id="a-threshold-value-of-zero",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                        "thresholds": [
                            {"name": "function_lines_of_code_warning", "value": "-"}
                        ],
                    }
                ]
            },
            (check_schema,),
            id="a-threshold-left-on-the-template-placeholder",
        ),
        pytest.param(
            {
                "rule_sets": [
                    {
                        "matching_content_path": "scripts/*.py",
                        "matching_content_path_doc": "x" * 200,
                        "rules": [{"name": "String Heavy Arguments", "weight": 0.0}],
                        "thresholds": [{"name": "function_lines_of_code_warning"}],
                    }
                ]
            },
            (check_schema,),
            id="a-threshold-with-no-value",
        ),
    ],
)
def test_the_checks_reject_known_bad_shapes(
    document: dict[str, object], failing_checks: tuple[Check, ...]
) -> None:
    """Each check must fail on the shapes that caused this.

    Without this the checks could assert nothing and still pass, which is the
    defect they exist to catch, one level up.
    """
    subject = RuleSets(document=document, root=REPOSITORY_ROOT)

    for check in failing_checks:
        with pytest.raises(AssertionError):
            check(subject)


# --- properties over documents nobody wrote down ----------------------------

#: A rule name in the prose form CodeScene uses, as two or more words.
PROSE_NAMES = st.lists(
    st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=1),
    min_size=2,
    max_size=4,
).map(" ".join)

#: A weight inside the documented range, Booleans excluded by construction.
WEIGHTS = st.one_of(
    st.integers(min_value=0, max_value=1).map(float),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)

RULES = st.lists(
    st.builds(lambda n, w: {"name": n, "weight": w}, PROSE_NAMES, WEIGHTS),
    min_size=0,
    max_size=4,
)

THRESHOLDS = st.lists(
    st.builds(
        lambda n, v: {"name": n, "value": v},
        st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1
        ),
        st.floats(
            min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
        ),
    ),
    min_size=0,
    max_size=3,
)

JUSTIFICATIONS = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=MINIMUM_JUSTIFICATION + 1,
    max_size=MINIMUM_JUSTIFICATION + 40,
)

#: A rule set that satisfies every check by construction. The glob is
#: fixed because the glob check reads the real repository, and the point
#: of these properties is the schema rather than the tree.
VALID_RULE_SETS = st.builds(
    lambda doc, rules, thresholds: {
        "matching_content_path": "scripts/*.py",
        "matching_content_path_doc": doc,
        "rules": rules,
        "thresholds": thresholds,
    },
    JUSTIFICATIONS,
    RULES,
    THRESHOLDS,
)

VALID_DOCUMENTS = st.builds(
    lambda rule_sets: {"usage": "generated", "rule_sets": rule_sets},
    st.lists(VALID_RULE_SETS, min_size=1, max_size=3),
)



@given(document=VALID_DOCUMENTS)
def test_a_well_formed_document_passes_every_check(
    document: dict[str, object],
) -> None:
    """Every check accepts any document built to the documented schema.

    The named fixtures pin a handful of good and bad shapes. They cannot
    show that the checks accept the schema generally rather than the one
    example written for them, and a check that rejected, say, an empty
    `rules` list or a rule set carrying no thresholds would pass all of
    them. These generate the schema instead.
    """
    subject = RuleSets(document=document, root=REPOSITORY_ROOT)
    for check in CHECKS:
        check(subject)


#: Each mutation of a valid document, with the check it must break. The
#: set is the fields the schema declares, so this is exhaustive over what
#: a rule set can carry rather than a sample of it.
MUTATIONS = (
    pytest.param(
        lambda rs: {**rs, "matching_content_path": "**/domain/*.rs"},
        check_globs_match,
        id="a-glob-that-matches-nothing",
    ),
    pytest.param(
        lambda rs: {k: v for k, v in rs.items() if k != "matching_content_path_doc"},
        check_justifications,
        id="the-justification-removed",
    ),
    pytest.param(
        lambda rs: {**rs, "matching_content_path_doc": "too short"},
        check_justifications,
        id="a-justification-below-the-minimum",
    ),
    pytest.param(
        lambda rs: {**rs, "matching_content_path_doc": ["x"] * 200},
        check_justifications,
        id="a-justification-that-is-not-prose",
    ),
    pytest.param(
        lambda rs: {**rs, "rules": [{"name": "hyphenated-slug", "weight": 0.0}]},
        check_schema,
        id="a-slug-where-a-prose-name-belongs",
    ),
    pytest.param(
        lambda rs: {**rs, "rules": [{"name": "String Heavy Arguments", "weight": 100}]},
        check_schema,
        id="a-threshold-where-a-weight-belongs",
    ),
    pytest.param(
        lambda rs: {**rs, "rules": ""},
        check_schema,
        id="rules-that-are-not-a-list",
    ),
    pytest.param(
        lambda rs: {**rs, "thresholds": {"function_lines_of_code_warning": 100}},
        check_schema,
        id="thresholds-as-a-mapping",
    ),
    pytest.param(
        lambda rs: {
            **rs,
            "thresholds": [{"name": "function_lines_of_code_warning", "value": "-"}],
        },
        check_schema,
        id="a-threshold-on-the-template-placeholder",
    ),
    pytest.param(
        lambda rs: {**rs, "unrecognized_key": "anything"},
        check_schema,
        id="a-key-codescene-would-ignore",
    ),
)


# `a-glob-that-matches-nothing` makes `check_globs_match` walk the whole
# repository for `**/domain/*.rs` and find none, which takes about a
# second here. That is filesystem traversal rather than the property, and
# it happens once per generated input, so the per-input deadline is not a
# meaningful bound on this test.
@settings(deadline=None)
@given(document=VALID_DOCUMENTS)
@pytest.mark.parametrize(("mutate", "broken"), MUTATIONS)
def test_each_mutation_of_a_valid_document_fails_its_check(
    document: dict[str, object],
    mutate: typ.Callable[[dict[str, object]], dict[str, object]],
    broken: Check,
) -> None:
    """Breaking one field of an otherwise valid document fails its check.

    Stated over generated documents rather than one fixture, so a check
    that happened to reject the fixture for an unrelated reason cannot
    stand in for the rule. The mutation is applied to the first rule set,
    which is enough: a check that stopped at the first offending entry
    and one that examined all of them both fail here, and the named
    fixtures cover the rest of the surface.
    """
    rule_sets = typ.cast("list[dict[str, object]]", document["rule_sets"])
    mutated = {**document, "rule_sets": [mutate(rule_sets[0]), *rule_sets[1:]]}
    with pytest.raises(AssertionError):
        broken(RuleSets(document=mutated, root=REPOSITORY_ROOT))
