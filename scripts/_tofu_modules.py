"""Registry of the OpenTofu example gates driven from the Makefile.

Each module's example is validated, planned and (where a plan policy exists)
checked with conftest. The recipes previously carried this configuration as
shell conditionals with per-module `-var` lists; holding it here lets one
script serve every module and lets the tests read the configuration directly.

Every gate is opt-in: when the module's kubeconfig variable is unset the gate
reports a skip, exactly as the shell recipes did.
"""

from __future__ import annotations

import dataclasses as dc
import os
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from collections.abc import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES_ROOT = Path("infra/modules")


class UnknownModuleError(KeyError):
    """Raised when a caller names a module that has no gate configuration."""


@dc.dataclass(frozen=True)
class TofuVar:
    """One ``-var`` assignment sourced from the environment.

    Attributes
    ----------
    name:
        The OpenTofu input variable name.
    env_var:
        The environment variable holding the value.
    default:
        Used when the environment value is unset or empty. A variable without
        a default must appear in :attr:`TofuModule.required_env`.
    """

    name: str
    env_var: str
    default: str | None = None

    def render(self, environ: Mapping[str, str]) -> str:
        """Return the ``-var`` argument for this assignment.

        Examples
        --------
        >>> TofuVar("branch", "BRANCH", default="main").render({})
        'branch=main'
        """
        value = environ.get(self.env_var) or self.default or ""
        return f"{self.name}={value}"


@dc.dataclass(frozen=True)
class PolicyCheck:
    """Conftest configuration for a module's plan policy."""

    policy_dir: Path
    namespace: str | None = None
    fail_on_warn: bool = False
    inline_data_env: str | None = None
    data_path_env: str | None = None


@dc.dataclass(frozen=True)
class TofuModule:
    """Everything the example gates need to know about one module."""

    key: str
    example_dir: Path
    gate_env: str
    required_env: tuple[str, ...] = ()
    validate_vars: tuple[TofuVar, ...] = ()
    plan_vars: tuple[TofuVar, ...] = ()
    policy: PolicyCheck | None = None

    @property
    def example_path(self) -> Path:
        """Absolute path of the example the gate operates on."""
        return REPO_ROOT / self.example_dir

    def is_enabled(self, environ: Mapping[str, str] | None = None) -> bool:
        """Return whether the operator has enabled this gate.

        Examples
        --------
        >>> MODULES["traefik"].is_enabled({})
        False
        """
        environ = os.environ if environ is None else environ
        return bool(environ.get(self.gate_env))

    def missing_requirements(
        self, environ: Mapping[str, str] | None = None
    ) -> dict[str, str | None]:
        """Return the required environment variables and their current values.

        Examples
        --------
        >>> sorted(MODULES["traefik"].missing_requirements({}))
        ['TRAEFIK_ACME_EMAIL', 'TRAEFIK_CLOUDFLARE_SECRET_NAME']
        """
        environ = os.environ if environ is None else environ
        return {name: environ.get(name) for name in self.required_env}

    def var_arguments(
        self,
        variables: tuple[TofuVar, ...],
        environ: Mapping[str, str] | None = None,
    ) -> list[str]:
        """Render ``variables`` as an OpenTofu argument list.

        Examples
        --------
        >>> MODULES["traefik"].var_arguments((), {})
        []
        """
        environ = os.environ if environ is None else environ
        arguments: list[str] = []
        for variable in variables:
            arguments.extend(["-var", variable.render(environ)])
        return arguments


def _example(module: str, name: str = "basic") -> Path:
    """Return the repository-relative path of a module example."""
    return MODULES_ROOT / module / "examples" / name


_TRAEFIK_VARS = (
    TofuVar("kubeconfig_path", "TRAEFIK_KUBECONFIG_PATH"),
    TofuVar("acme_email", "TRAEFIK_ACME_EMAIL"),
    TofuVar("cloudflare_api_token_secret_name", "TRAEFIK_CLOUDFLARE_SECRET_NAME"),
)

_EXTERNAL_DNS_VARS = (
    TofuVar("kubeconfig_path", "EXTERNAL_DNS_KUBECONFIG_PATH"),
    TofuVar("domain_filters", "EXTERNAL_DNS_DOMAIN_FILTERS"),
    TofuVar("txt_owner_id", "EXTERNAL_DNS_TXT_OWNER_ID"),
    TofuVar("cloudflare_api_token_secret_name", "EXTERNAL_DNS_CLOUDFLARE_SECRET_NAME"),
)

_CERT_MANAGER_VARS = (
    TofuVar("kubeconfig_path", "CERT_MANAGER_KUBECONFIG_PATH"),
    TofuVar("acme_email", "CERT_MANAGER_ACME_EMAIL"),
    TofuVar("namecheap_api_secret_name", "CERT_MANAGER_NAMECHEAP_SECRET_NAME"),
    TofuVar("vault_server", "CERT_MANAGER_VAULT_SERVER"),
    TofuVar("vault_pki_path", "CERT_MANAGER_VAULT_PKI_PATH"),
    TofuVar("vault_token_secret_name", "CERT_MANAGER_VAULT_TOKEN_SECRET_NAME"),
    TofuVar("vault_ca_bundle_pem", "CERT_MANAGER_VAULT_CA_BUNDLE_PEM"),
)

_VAULT_ESO_VARS = (
    TofuVar("vault_address", "VAULT_ESO_VAULT_ADDRESS"),
    TofuVar("vault_ca_bundle_pem", "VAULT_ESO_CA_BUNDLE_PEM"),
    TofuVar("approle_role_id", "VAULT_ESO_APPROLE_ROLE_ID"),
    TofuVar("approle_secret_id", "VAULT_ESO_APPROLE_SECRET_ID"),
    TofuVar("kubeconfig_path", "VAULT_ESO_KUBECONFIG_PATH"),
)

_FLUXCD_KUBECONFIG = TofuVar("kubeconfig_path", "FLUX_KUBECONFIG_PATH")

# The Flux example plans against a public sample repository unless the
# operator points it elsewhere; these defaults match the previous recipe.
_FLUXCD_PLAN_VARS = (
    TofuVar(
        "git_repository_url",
        "FLUX_GIT_REPOSITORY_URL",
        default="https://github.com/fluxcd/flux2-kustomize-helm-example.git",
    ),
    TofuVar(
        "git_repository_path",
        "FLUX_GIT_REPOSITORY_PATH",
        default="./clusters/my-cluster",
    ),
    TofuVar("git_repository_branch", "FLUX_GIT_REPOSITORY_BRANCH", default="main"),
    _FLUXCD_KUBECONFIG,
)


MODULES: dict[str, TofuModule] = {
    module.key: module
    for module in (
        TofuModule(
            key="fluxcd",
            example_dir=_example("fluxcd"),
            gate_env="FLUX_KUBECONFIG_PATH",
            validate_vars=(_FLUXCD_KUBECONFIG,),
            plan_vars=_FLUXCD_PLAN_VARS,
            policy=PolicyCheck(
                policy_dir=MODULES_ROOT / "fluxcd" / "policy",
                inline_data_env="FLUX_POLICY_PARAMS_JSON",
                data_path_env="FLUX_POLICY_DATA",
            ),
        ),
        TofuModule(
            key="traefik",
            example_dir=_example("traefik"),
            gate_env="TRAEFIK_KUBECONFIG_PATH",
            required_env=("TRAEFIK_ACME_EMAIL", "TRAEFIK_CLOUDFLARE_SECRET_NAME"),
            validate_vars=_TRAEFIK_VARS,
            plan_vars=_TRAEFIK_VARS,
            policy=PolicyCheck(
                policy_dir=MODULES_ROOT / "traefik" / "policy" / "plan",
                namespace="traefik.policy.plan",
                fail_on_warn=True,
            ),
        ),
        TofuModule(
            key="external-dns",
            example_dir=_example("external_dns"),
            gate_env="EXTERNAL_DNS_KUBECONFIG_PATH",
            required_env=(
                "EXTERNAL_DNS_DOMAIN_FILTERS",
                "EXTERNAL_DNS_TXT_OWNER_ID",
                "EXTERNAL_DNS_CLOUDFLARE_SECRET_NAME",
            ),
            validate_vars=_EXTERNAL_DNS_VARS,
            plan_vars=_EXTERNAL_DNS_VARS,
            policy=PolicyCheck(
                policy_dir=MODULES_ROOT / "external_dns" / "policy" / "plan",
                namespace="external_dns.policy.plan",
                fail_on_warn=True,
            ),
        ),
        TofuModule(
            key="cert-manager",
            example_dir=_example("cert_manager"),
            gate_env="CERT_MANAGER_KUBECONFIG_PATH",
            required_env=(
                "CERT_MANAGER_ACME_EMAIL",
                "CERT_MANAGER_NAMECHEAP_SECRET_NAME",
                "CERT_MANAGER_VAULT_SERVER",
                "CERT_MANAGER_VAULT_PKI_PATH",
                "CERT_MANAGER_VAULT_TOKEN_SECRET_NAME",
                "CERT_MANAGER_VAULT_CA_BUNDLE_PEM",
            ),
            validate_vars=_CERT_MANAGER_VARS,
            plan_vars=_CERT_MANAGER_VARS,
            policy=PolicyCheck(
                policy_dir=MODULES_ROOT / "cert_manager" / "policy" / "plan",
                namespace="cert_manager.policy.plan",
                fail_on_warn=True,
            ),
        ),
        TofuModule(
            key="vault-eso",
            example_dir=_example("vault_eso"),
            gate_env="VAULT_ESO_KUBECONFIG_PATH",
            required_env=(
                "VAULT_ESO_VAULT_ADDRESS",
                "VAULT_ESO_CA_BUNDLE_PEM",
                "VAULT_ESO_APPROLE_ROLE_ID",
                "VAULT_ESO_APPROLE_SECRET_ID",
            ),
            validate_vars=_VAULT_ESO_VARS,
            plan_vars=_VAULT_ESO_VARS,
            policy=PolicyCheck(
                policy_dir=MODULES_ROOT / "vault_eso" / "policy" / "plan",
                namespace="vault_eso.policy.plan",
                fail_on_warn=True,
            ),
        ),
    )
}


def get_module(key: str) -> TofuModule:
    """Return the gate configuration for ``key``.

    Examples
    --------
    >>> get_module("traefik").gate_env
    'TRAEFIK_KUBECONFIG_PATH'
    """
    try:
        return MODULES[key]
    except KeyError as exc:
        known = ", ".join(sorted(MODULES))
        message = f"unknown module {key!r}; expected one of: {known}"
        raise UnknownModuleError(message) from exc
