"""Helpers shared by the OpenTofu gate tests.

The gates drive one binary, ``tofu``, through several subcommands, so the
doubles dispatch on the subcommand rather than on the whole argument list.
"""

from __future__ import annotations

import typing as typ

from cmd_mox import Invocation, Response

if typ.TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from cmd_mox import CmdMox

    from scripts._tofu_modules import TofuModule

TRAEFIK_ENVIRONMENT = {
    "TRAEFIK_KUBECONFIG_PATH": "/tmp/kubeconfig",
    "TRAEFIK_ACME_EMAIL": "ops@example.test",
    "TRAEFIK_CLOUDFLARE_SECRET_NAME": "cloudflare-token",
}


def subcommand_of(args: list[str]) -> str:
    """Return the OpenTofu subcommand from an argument list.

    ``-chdir`` precedes the subcommand, so the first argument that is not an
    option identifies the step.

    Examples
    --------
    >>> subcommand_of(["-chdir=example", "plan", "-no-color"])
    'plan'
    """
    for argument in args:
        if not argument.startswith("-"):
            return argument
    return ""


def tofu_handler(
    exit_codes: Mapping[str, int], stdout: Mapping[str, str] | None = None
) -> Callable[[Invocation], Response]:
    """Build a ``tofu`` double that answers per subcommand.

    Examples
    --------
    >>> handler = tofu_handler({"validate": 1})
    """
    outputs = dict(stdout or {})

    def handler(invocation: Invocation) -> Response:
        """Answer one ``tofu`` invocation according to its subcommand."""
        subcommand = subcommand_of(list(invocation.args))
        return Response(
            stdout=outputs.get(subcommand, ""),
            exit_code=exit_codes.get(subcommand, 0),
        )

    return handler


def stub_tofu(
    mox: CmdMox,
    exit_codes: Mapping[str, int] | None = None,
    stdout: Mapping[str, str] | None = None,
) -> None:
    """Register a ``tofu`` double dispatching on the subcommand.

    Examples
    --------
    >>> # stub_tofu(cmd_mox, {"validate": 1})
    """
    mox.stub("tofu").runs(tofu_handler(exit_codes or {}, stdout))


def tofu_calls(mox: CmdMox) -> list[str]:
    """Return the OpenTofu subcommands recorded during replay, in order.

    Examples
    --------
    >>> # tofu_calls(cmd_mox) == ["validate", "plan"]
    """
    return [
        subcommand_of(list(invocation.args))
        for invocation in mox.journal
        if invocation.command == "tofu"
    ]


def module_environment(module: TofuModule) -> dict[str, str]:
    """Return a complete, distinct environment for ``module``'s gate.

    Every declared variable gets a value derived from its name, so an
    assertion can tell which variable a `-var` assignment came from.

    Examples
    --------
    >>> # module_environment(MODULES["traefik"])["TRAEFIK_ACME_EMAIL"]
    """
    environment = {module.gate_env: f"value-for-{module.gate_env}"}
    for name in module.required_env:
        environment[name] = f"value-for-{name}"
    for variable in (*module.validate_vars, *module.plan_vars):
        environment.setdefault(variable.env_var, f"value-for-{variable.env_var}")
    return environment
