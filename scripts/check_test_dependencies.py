#!/usr/bin/env python3
"""Pre-flight validation for infrastructure test dependencies.

This script verifies that required command-line tools for Terraform and policy
integration tests are available before test execution. Run it as a CI step or
locally prior to invoking the infrastructure-oriented Go test suites to avoid
silent skips caused by missing binaries.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Dependency:
    """Represents a required binary for the infrastructure test suites."""

    name: str
    description: str
    minimum_version: str | None = None
    minimum_opa_version: str | None = None
    version_args: tuple[str, ...] = ("--version",)

    def minimum_version_label(self) -> str:
        """Return a human-readable minimum version requirement for documentation."""

        if self.minimum_version is None and self.minimum_opa_version is None:
            return "n/a"

        if self.minimum_version is None:
            return f"OPA >= {self.minimum_opa_version}"

        if self.minimum_opa_version is None:
            return self.minimum_version

        return f"{self.minimum_version} (OPA >= {self.minimum_opa_version})"


@dataclass(frozen=True)
class VersionProbeResult:
    """Outcome of invoking a dependency's version command."""

    parsed_version: str | None
    raw_output: str | None


REQUIRED_DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency(
        "tofu",
        "OpenTofu CLI for Terraform plan execution",
        minimum_version="1.7.0",
        version_args=("version",),
    ),
    Dependency(
        "conftest",
        "Policy testing via Open Policy Agent",
        minimum_version="0.45.0",
        minimum_opa_version="0.59.0",
    ),
)

ALLOWED_DEPENDENCIES = {
    dependency.name: dependency for dependency in REQUIRED_DEPENDENCIES
}

VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")
OPA_VERSION_PATTERN = re.compile(
    r"^OPA(?: Version)?:\s*v?(\d+(?:\.\d+)+)\s*$", re.MULTILINE
)


def collect_missing(dependencies: Iterable[Dependency]) -> list[Dependency]:
    """Return the subset of dependencies that are not discoverable on PATH.

    Parameters
    ----------
    dependencies : Iterable[Dependency]
        The collection of dependencies to validate.

    Returns
    -------
    list[Dependency]
        Dependencies whose executables are not found on the system PATH.

    Examples
    --------
    >>> collect_missing([])
    []
    """

    return [
        dependency
        for dependency in dependencies
        if shutil.which(dependency.name) is None
    ]


def to_int_tuple(version: str) -> tuple[int, ...]:
    """Convert a dotted version string into a tuple of integers.

    Parameters
    ----------
    version : str
        A version string with dot-separated numeric components (for example,
        ``"1.7.0"``).

    Returns
    -------
    tuple[int, ...]
        The integer components of the supplied version string.

    Examples
    --------
    >>> to_int_tuple("1.7.0")
    (1, 7, 0)
    """

    return tuple(int(part) for part in version.split("."))


def is_version_sufficient(installed: str, minimum: str) -> bool:
    """Return ``True`` if the installed version satisfies the minimum requirement.

    Parameters
    ----------
    installed : str
        The installed version string.
    minimum : str
        The minimum required version string.

    Returns
    -------
    bool
        True if the installed version meets or exceeds the minimum version.

    Examples
    --------
    >>> is_version_sufficient("1.2.0", "1.1.0")
    True
    """

    installed_parts = to_int_tuple(installed)
    minimum_parts = to_int_tuple(minimum)
    max_length = max(len(installed_parts), len(minimum_parts))
    installed_normalised = installed_parts + (0,) * (max_length - len(installed_parts))
    minimum_normalised = minimum_parts + (0,) * (max_length - len(minimum_parts))
    return installed_normalised >= minimum_normalised


def parse_version_from_output(
    output: str,
    pattern: re.Pattern[str] = VERSION_PATTERN,
) -> str | None:
    """Extract a dotted version string from command output.

    Parameters
    ----------
    output : str
        The raw output from a version command.
    pattern : re.Pattern[str], optional
        Regex to extract the dotted version string. The first capture group must
        contain the version.

    Returns
    -------
    str | None
        The extracted version string, or None if no version pattern is found.

    Examples
    --------
    >>> parse_version_from_output("tofu version 1.7.1")
    '1.7.1'
    >>> parse_version_from_output("Conftest: 0.63.0\\nOPA: 1.9.0", pattern=OPA_VERSION_PATTERN)
    '1.9.0'
    """

    return _parse_version_from_pattern(output, pattern)


def _parse_version_from_pattern(output: str, pattern: re.Pattern[str]) -> str | None:
    """Extract a dotted version string from the first regex match group."""

    match = pattern.search(output)
    if match is None:
        return None
    try:
        return match.group(1)
    except IndexError:
        return None


def _validate_minimum_version(
    dependency: Dependency,
    probe: VersionProbeResult,
) -> str | None:
    """Return the failing version detail if the probe is below the minimum."""
    if dependency.minimum_version is None:
        return None
    if probe.parsed_version is None:
        return probe.raw_output or ""
    if not is_version_sufficient(probe.parsed_version, dependency.minimum_version):
        return probe.raw_output or probe.parsed_version
    return None


def _validate_minimum_opa_version(
    dependency: Dependency,
    probe: VersionProbeResult,
) -> str | None:
    """Return the failing OPA version detail if it is below the OPA minimum."""
    if dependency.minimum_opa_version is None:
        return None
    if probe.raw_output is None:
        return ""

    opa_version = parse_version_from_output(probe.raw_output, pattern=OPA_VERSION_PATTERN)
    if opa_version is None:
        return probe.raw_output
    if not is_version_sufficient(opa_version, dependency.minimum_opa_version):
        return f"OPA {opa_version}"
    return None


def _validate_dependency_requirements(
    dependency: Dependency,
) -> str | None:
    """Probe a dependency when it sets a minimum and return any version failure."""
    if dependency.minimum_version is None and dependency.minimum_opa_version is None:
        return None

    probe = probe_version(dependency)
    version_failure = _validate_minimum_version(dependency, probe)
    if version_failure is not None:
        return version_failure

    return _validate_minimum_opa_version(dependency, probe)


def _validate_dependency_safety(dependency: Dependency) -> Dependency:
    """Ensure the dependency matches the allow-listed command configuration.

    Parameters
    ----------
    dependency : Dependency
        The dependency configuration proposed for a version probe.

    Returns
    -------
    Dependency
        The canonical allow-listed dependency configuration.

    Raises
    ------
    ValueError
        If the dependency is not recognised or its version arguments differ
        from the allow-listed configuration.

    Examples
    --------
    >>> _validate_dependency_safety(REQUIRED_DEPENDENCIES[0]).version_args
    ('version',)
    """

    allowed_dependency = ALLOWED_DEPENDENCIES.get(dependency.name)
    if allowed_dependency is None:
        raise ValueError(
            "Refusing to execute version probe for unrecognised dependency name"
        )
    if dependency.version_args != allowed_dependency.version_args:
        raise ValueError(
            "Refusing to execute version probe for unexpected argument sequence"
        )
    return allowed_dependency


def _execute_version_command(dependency: Dependency) -> str | None:
    """Execute the version command for a dependency and capture its output.

    Parameters
    ----------
    dependency : Dependency
        The allow-listed dependency to probe.

    Returns
    -------
    str | None
        The combined standard output or standard error emitted by the version
        command, stripped of trailing whitespace, or ``None`` if the command
        failed or produced no output.

    Examples
    --------
    >>> _execute_version_command(REQUIRED_DEPENDENCIES[0]) is None
    True
    """

    command = [dependency.name, *dependency.version_args]
    # NOTE: ``dependency`` originates from ``_validate_dependency_safety`` which
    # constrains both the executable name and argument vector to a known
    # allow-list, preventing user-controlled input reaching this subprocess call.
    try:
        process = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    output = process.stdout.strip() or process.stderr.strip()
    return output or None


def probe_version(dependency: Dependency) -> VersionProbeResult:
    """Run the version command for a dependency and parse the response.

    Parameters
    ----------
    dependency : Dependency
        The dependency to probe.

    Returns
    -------
    VersionProbeResult
        The parsed version and raw output, or None values if the probe fails.

    Raises
    ------
    ValueError
        If the dependency name is not in the allowed list or if the version
        arguments do not match the expected sequence.

    Examples
    --------
    >>> probe_version(REQUIRED_DEPENDENCIES[0]).raw_output is None
    True
    """

    allowed_dependency = _validate_dependency_safety(dependency)
    output = _execute_version_command(allowed_dependency)
    if output is None:
        return VersionProbeResult(parsed_version=None, raw_output=None)

    parsed_version = parse_version_from_output(output)
    return VersionProbeResult(parsed_version=parsed_version, raw_output=output)


def validate_dependencies(
    dependencies: Iterable[Dependency],
) -> tuple[list[Dependency], list[tuple[Dependency, str | None]]]:
    """Check for missing dependencies and incompatible versions.

    Parameters
    ----------
    dependencies : Iterable[Dependency]
        The dependencies to validate.

    Returns
    -------
    tuple[list[Dependency], list[tuple[Dependency, str | None]]]
        A pair containing the missing dependencies and the dependencies whose
        versions could not be validated or failed the minimum requirement. Each
        incompatible dependency is paired with the raw version output when
        available.

    Examples
    --------
    >>> validate_dependencies(REQUIRED_DEPENDENCIES)
    ([], [])
    """

    missing = collect_missing(dependencies)
    missing_names = {dependency.name for dependency in missing}
    incompatible: list[tuple[Dependency, str | None]] = []

    for dependency in dependencies:
        if dependency.name in missing_names:
            continue

        failure = _validate_dependency_requirements(dependency)
        if failure is not None:
            incompatible.append((dependency, failure))

    return missing, incompatible


def format_failure_message(
    missing: Iterable[Dependency],
    incompatible: Iterable[tuple[Dependency, str | None]],
) -> str:
    """Create a human-readable report for dependency validation failures.

    Parameters
    ----------
    missing : Iterable[Dependency]
        Dependencies that were not found on the system ``PATH``.
    incompatible : Iterable[tuple[Dependency, str | None]]
        Dependencies paired with the raw output from their version probe when
        the detected version could not be parsed or failed the minimum
        requirement.

    Returns
    -------
    str
        A formatted multi-line message that lists missing dependencies and
        those that require an upgrade.

    Examples
    --------
    >>> format_failure_message([], [])
    'Required test dependencies failed validation.'
    """

    missing_list = list(missing)
    incompatible_list = list(incompatible)

    lines = ["Required test dependencies failed validation."]

    if missing_list:
        lines.append("")
        lines.append(
            "Install the following tools before running the infrastructure tests:"
        )
        lines.extend(
            f"  - {dependency.name}: {dependency.description}"
            for dependency in missing_list
        )

    lines.extend(
        _format_incompatible_dependencies(
            incompatible_list,
            include_separator=bool(missing_list),
        )
    )

    lines.extend(
        [
            "",
            "Refer to docs/infrastructure-test-dependencies.md for installation guidance.",
        ]
    )
    return "\n".join(lines)


def _format_requirement_label(required: str) -> str:
    """Prefix ">= " to a version requirement unless it already names OPA."""
    if required.startswith("OPA >="):
        return required
    return f">= {required}"


def _format_incompatible_dependencies(
    incompatible: list[tuple[Dependency, str | None]],
    *,
    include_separator: bool,
) -> list[str]:
    """Build report lines for incompatible tools, optionally led by a blank line."""
    if not incompatible:
        return []

    lines: list[str] = []
    if include_separator:
        lines.append("")

    lines.append("Update the following tools to satisfy minimum supported versions:")
    for dependency, detected in incompatible:
        required = dependency.minimum_version_label()
        observed = (detected or "unknown").splitlines()[0]
        requirement = _format_requirement_label(required)
        lines.append(f"  - {dependency.name}: found {observed}, require {requirement}")

    return lines


def format_markdown_table(dependencies: Sequence[Dependency]) -> str:
    """Render a Markdown table describing dependencies.

    Parameters
    ----------
    dependencies : Sequence[Dependency]
        The dependencies to include in the table.

    Returns
    -------
    str
        A Markdown-formatted table with columns for the tool name, minimum
        supported version, and purpose.

    Examples
    --------
    >>> format_markdown_table(REQUIRED_DEPENDENCIES).splitlines()[0]
    '| Tool | Minimum version | Purpose |'
    """

    lines = [
        "| Tool | Minimum version | Purpose |",
        "| ---- | ---------------- | ------- |",
    ]
    lines.extend(
        f"| `{dependency.name}` | {dependency.minimum_version_label()} | {dependency.description} |"
        for dependency in dependencies
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line interface for the script.

    Returns
    -------
    argparse.ArgumentParser
        The configured argument parser for the dependency validation script.

    Examples
    --------
    >>> build_parser().parse_args(["--emit-markdown"]).emit_markdown
    True
    """

    parser = argparse.ArgumentParser(
        description=(
            "Validate command-line dependencies for the infrastructure test suites "
            "or emit documentation describing the required tooling."
        )
    )
    parser.add_argument(
        "--emit-markdown",
        action="store_true",
        help="Print a Markdown table of required dependencies and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the pre-flight dependency check.

    Parse command-line arguments, validate required dependencies, and write
    diagnostic output to stdout or stderr.

    Parameters
    ----------
    argv : Sequence[str] | None, optional
        The command-line arguments to parse. If ``None``, defaults to
        ``sys.argv``.

    Returns
    -------
    int
        Exit status: 0 if all dependencies are present and compatible, or if
        the ``--emit-markdown`` flag is used; 1 if any dependencies are
        missing or incompatible.

    Examples
    --------
    >>> main(["--emit-markdown"])
    0
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.emit_markdown:
        sys.stdout.write(format_markdown_table(REQUIRED_DEPENDENCIES) + "\n")
        return 0

    missing, incompatible = validate_dependencies(REQUIRED_DEPENDENCIES)
    if missing or incompatible:
        sys.stderr.write(format_failure_message(missing, incompatible) + "\n")
        return 1

    sys.stdout.write("All required test dependencies are present and compatible.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
