"""Property tests for the shell-command classifier.

The parametrized shapes cover the forms someone thought to write down. The
hazard is the form nobody did: a separator hidden inside quoting, escaping, a
substitution, a subshell or a brace group, or a `||` list that only looks like
a pipeline.

Commands are assembled from fragments whose context is known by construction,
so the expected separator offsets are recorded while the string is built
rather than recomputed by a second implementation of the rule.
"""

from __future__ import annotations

import typing as typ

from hypothesis import given, settings
from hypothesis import strategies as st
from makefile_contract_support import (
    command_separators,
    is_single_command,
    pipeline_separators,
)

if typ.TYPE_CHECKING:
    from collections.abc import Sequence

SAFE_WORD = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz-_./="),
    min_size=1,
    max_size=6,
)

# Every fragment holds a `;` or a `|` that is not a top-level separator.
HIDDEN_FRAGMENT = st.sampled_from(
    [
        "'inner;text|here'",
        '"inner;text|here"',
        "$(inner;text|here)",
        "(inner;text|here)",
        "{ inner;text; }",
        r"escaped\;semicolon",
        r"escaped\|pipe",
        "left||right",
        "left&&right",
    ]
)

STAGE_ELEMENT = st.one_of(SAFE_WORD, HIDDEN_FRAGMENT)
SEPARATOR = st.sampled_from([";", "|"])


class Command(typ.NamedTuple):
    """A generated command line and the offsets of its real separators."""

    text: str
    semicolons: list[int]
    pipes: list[int]


def _assemble(stages: Sequence[Sequence[str]], separators: Sequence[str]) -> Command:
    """Join ``stages`` with ``separators``, recording each separator's offset."""
    text = ""
    semicolons: list[int] = []
    pipes: list[int] = []

    for index, stage in enumerate(stages):
        if index:
            text += " "
            separator = separators[index - 1]
            offsets = semicolons if separator == ";" else pipes
            offsets.append(len(text))
            text += f"{separator} "
        text += " ".join(stage)

    return Command(text=text, semicolons=semicolons, pipes=pipes)


@st.composite
def command_lines(draw: st.DrawFn) -> Command:
    """Build a command line whose real separator offsets are known."""
    stages = draw(
        st.lists(
            st.lists(STAGE_ELEMENT, min_size=1, max_size=3),
            min_size=1,
            max_size=4,
        )
    )
    separators = draw(
        st.lists(SEPARATOR, min_size=len(stages) - 1, max_size=len(stages) - 1)
    )
    return _assemble(stages, separators)


@settings(deadline=None, max_examples=200)
@given(command=command_lines())
def test_only_real_separators_are_reported(command: Command) -> None:
    """Quoted, escaped and grouped separators are never counted."""
    assert command_separators(command.text) == command.semicolons, (
        f"wrong semicolon offsets for {command.text!r}"
    )
    assert pipeline_separators(command.text) == command.pipes, (
        f"wrong pipe offsets for {command.text!r}"
    )


@settings(deadline=None, max_examples=200)
@given(command=command_lines())
def test_single_command_agrees_with_the_separators(command: Command) -> None:
    """A command is single exactly when it has no separator of either kind."""
    expected = not command.semicolons and not command.pipes

    assert is_single_command(command.text) is expected, (
        f"{command.text!r} should{'' if expected else ' not'} be a single command"
    )


@settings(deadline=None, max_examples=200)
@given(stage=st.lists(STAGE_ELEMENT, min_size=1, max_size=4))
def test_a_lone_stage_is_always_one_command(stage: list[str]) -> None:
    """No fragment on its own turns a command into a chain."""
    text = " ".join(stage)

    assert is_single_command(text), f"{text!r} was misread as several commands"
