#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=2.9"]
# ///
"""Render platform manifests via OpenTofu.

This script:
- creates a temporary workspace for the platform_render module;
- runs tofu init and apply to render manifests;
- extracts rendered_manifests output; and
- writes manifests to the output directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cyclopts import App, Parameter
from scripts._infra_k8s import (
    InfraK8sError,
    TofuCommandError,
    append_github_env,
    run_tofu,
    tofu_output,
    write_manifests,
    write_tfvars,
)
from scripts._render_platform_inputs import (
    RawRenderInputs,
    RenderInputs,
    build_render_tfvars,
    resolve_render_inputs,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_RENDER_PATH = REPO_ROOT / "infra" / "modules" / "platform_render"

app = App(help="Render platform manifests via OpenTofu.")

CLUSTER_NAME_PARAM = Parameter()
DOMAIN_PARAM = Parameter()
ACME_EMAIL_PARAM = Parameter()
CLOUDFLARE_API_TOKEN_SECRET_NAME_PARAM = Parameter()
VAULT_ADDRESS_PARAM = Parameter()
VAULT_ROLE_ID_PARAM = Parameter()
VAULT_SECRET_ID_PARAM = Parameter()
VAULT_CA_CERTIFICATE_PARAM = Parameter()
ENABLE_TRAEFIK_PARAM = Parameter()
ENABLE_CERT_MANAGER_PARAM = Parameter()
ENABLE_EXTERNAL_DNS_PARAM = Parameter()
ENABLE_VAULT_ESO_PARAM = Parameter()
ENABLE_CNPG_PARAM = Parameter()
RUNNER_TEMP_PARAM = Parameter()
OUTPUT_DIR_PARAM = Parameter()
GITHUB_ENV_PARAM = Parameter()


def _run_tofu_or_raise(command_name: str, args: list[str], module_path: Path) -> None:
    """Run an OpenTofu command and raise on failure.

    Parameters
    ----------
    command_name : str
        Human-readable name for error messages (e.g., "init", "apply").
    args : list[str]
        Command arguments to pass to run_tofu.
    module_path : Path
        Working directory for the command.
    """
    print(f"\n--- Running tofu {command_name} ---")
    result = run_tofu(args, module_path)
    if not result.success:
        err_msg = f"tofu {command_name} failed: {result.stderr}"
        print(f"error: {err_msg}", file=sys.stderr)
        raise TofuCommandError(err_msg)
    print(result.stdout)


def _extract_rendered_manifests(outputs: dict[str, object]) -> dict[str, str]:
    """Extract rendered manifests from OpenTofu outputs.

    Handles both direct output format and wrapped format where the value
    is nested under a "value" key.
    """
    if "rendered_manifests" not in outputs:
        return {}
    manifests_raw = outputs["rendered_manifests"]
    if not isinstance(manifests_raw, dict):
        msg = "rendered_manifests output must be a map"
        raise TypeError(msg)
    if "value" in manifests_raw:
        manifests_raw = manifests_raw["value"]
        if not isinstance(manifests_raw, dict):
            msg = "rendered_manifests value must be a map"
            raise TypeError(msg)
    return {str(path): str(content) for path, content in manifests_raw.items()}


def render_manifests(inputs: RenderInputs, tfvars: dict[str, object]) -> dict[str, str]:
    """Run OpenTofu to render platform manifests.

    Returns a dict mapping relative paths to YAML content.

    Examples
    --------
    The call needs OpenTofu on the path, so it is marked as not run. It
    said as much in a comment before, which `doctest` does not read: the
    example executed on every run of the documentation gate, invoked
    `tofu`, and wrote a variables file under the runner temporary
    directory it names. The paths are a workspace relative to the
    working directory for the same reason.

    >>> from pathlib import Path
    >>> workspace = Path("workspace")
    >>> inputs = RenderInputs(
    ...     cluster_name="preview-1",
    ...     domain="example.com",
    ...     acme_email="ops@example.com",
    ...     cloudflare_api_token_secret_name="cloudflare-token",
    ...     vault_address=None,
    ...     vault_role_id=None,
    ...     vault_secret_id=None,
    ...     vault_ca_certificate=None,
    ...     enable_traefik=True,
    ...     enable_cert_manager=True,
    ...     enable_external_dns=True,
    ...     enable_vault_eso=False,
    ...     enable_cnpg=False,
    ...     runner_temp=workspace,
    ...     output_dir=workspace / "output",
    ...     github_env=workspace / "github-env",
    ... )
    >>> tfvars = {"cluster_name": "preview-1", "domain": "example.com"}
    >>> render_manifests(inputs, tfvars)  # doctest: +SKIP
    {'manifests/namespace.yaml': 'apiVersion: v1\\nkind: Namespace\\n'}
    """
    work_dir = inputs.runner_temp / "render-manifests"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Write tfvars to temp file
    var_file = work_dir / "platform.tfvars.json"
    write_tfvars(var_file, tfvars)

    print(f"Rendering platform manifests for cluster '{inputs.cluster_name}'...")
    print(f"  Domain: {inputs.domain}")
    print(f"  Traefik: {inputs.enable_traefik}")
    print(f"  cert-manager: {inputs.enable_cert_manager}")
    print(f"  external-dns: {inputs.enable_external_dns}")
    print(f"  vault-eso: {inputs.enable_vault_eso}")
    print(f"  CNPG: {inputs.enable_cnpg}")

    _run_tofu_or_raise("init", ["init", "-input=false"], PLATFORM_RENDER_PATH)
    _run_tofu_or_raise(
        "apply",
        ["apply", "-auto-approve", "-input=false", f"-var-file={var_file}"],
        PLATFORM_RENDER_PATH,
    )

    print("\n--- Extracting rendered manifests ---")
    outputs_raw = tofu_output(PLATFORM_RENDER_PATH)
    if not isinstance(outputs_raw, dict):
        msg = "tofu output returned unexpected data"
        raise TypeError(msg)
    return _extract_rendered_manifests(outputs_raw)


def _build_raw_inputs(
    cluster_name: str | None,
    domain: str | None,
    acme_email: str | None,
    cloudflare_api_token_secret_name: str | None,
    vault_address: str | None,
    vault_role_id: str | None,
    vault_secret_id: str | None,
    vault_ca_certificate: str | None,
    enable_traefik: str | None,
    enable_cert_manager: str | None,
    enable_external_dns: str | None,
    enable_vault_eso: str | None,
    enable_cnpg: str | None,
    runner_temp: Path | None,
    output_dir: Path | None,
    github_env: Path | None,
) -> RawRenderInputs:
    """Construct RawRenderInputs from CLI parameters."""
    return RawRenderInputs(
        cluster_name=cluster_name,
        domain=domain,
        acme_email=acme_email,
        cloudflare_api_token_secret_name=cloudflare_api_token_secret_name,
        vault_address=vault_address,
        vault_role_id=vault_role_id,
        vault_secret_id=vault_secret_id,
        vault_ca_certificate=vault_ca_certificate,
        enable_traefik=enable_traefik,
        enable_cert_manager=enable_cert_manager,
        enable_external_dns=enable_external_dns,
        enable_vault_eso=enable_vault_eso,
        enable_cnpg=enable_cnpg,
        runner_temp=runner_temp,
        output_dir=output_dir,
        github_env=github_env,
    )


def _handle_manifest_output(
    inputs: RenderInputs,
    manifests: dict[str, str],
) -> int:
    """Write manifests to disk and export environment variables.

    Returns the number of manifests written.
    """
    inputs.output_dir.mkdir(parents=True, exist_ok=True)
    count = write_manifests(inputs.output_dir, manifests)
    append_github_env(
        inputs.github_env,
        {
            "RENDERED_MANIFEST_COUNT": str(count),
            "RENDER_OUTPUT_DIR": str(inputs.output_dir),
        },
    )
    if count == 0:
        print("Rendered 0 manifests; exported outputs for downstream steps.")
    else:
        print(f"Rendered {count} manifests to {inputs.output_dir}.")
    return count


@app.command()
def main(
    cluster_name: str | None = CLUSTER_NAME_PARAM,
    domain: str | None = DOMAIN_PARAM,
    acme_email: str | None = ACME_EMAIL_PARAM,
    cloudflare_api_token_secret_name: str | None = CLOUDFLARE_API_TOKEN_SECRET_NAME_PARAM,
    vault_address: str | None = VAULT_ADDRESS_PARAM,
    vault_role_id: str | None = VAULT_ROLE_ID_PARAM,
    vault_secret_id: str | None = VAULT_SECRET_ID_PARAM,
    vault_ca_certificate: str | None = VAULT_CA_CERTIFICATE_PARAM,
    enable_traefik: str | None = ENABLE_TRAEFIK_PARAM,
    enable_cert_manager: str | None = ENABLE_CERT_MANAGER_PARAM,
    enable_external_dns: str | None = ENABLE_EXTERNAL_DNS_PARAM,
    enable_vault_eso: str | None = ENABLE_VAULT_ESO_PARAM,
    enable_cnpg: str | None = ENABLE_CNPG_PARAM,
    runner_temp: Path | None = RUNNER_TEMP_PARAM,
    output_dir: Path | None = OUTPUT_DIR_PARAM,
    github_env: Path | None = GITHUB_ENV_PARAM,
) -> int:
    """Render platform manifests via OpenTofu.

    Inputs are resolved from CLI arguments and environment variables, OpenTofu
    renders platform manifests, and the output count is exported to GITHUB_ENV.

    Examples
    --------
    Needs OpenTofu and a reachable Vault, so it is marked as not run.

    >>> from pathlib import Path
    >>> main(
    ...     cluster_name="preview-1",
    ...     domain="example.com",
    ...     acme_email="ops@example.com",
    ...     github_env=Path("workspace") / "github-env",
    ... )  # doctest: +SKIP
    0
    """
    raw_inputs = _build_raw_inputs(
        cluster_name,
        domain,
        acme_email,
        cloudflare_api_token_secret_name,
        vault_address,
        vault_role_id,
        vault_secret_id,
        vault_ca_certificate,
        enable_traefik,
        enable_cert_manager,
        enable_external_dns,
        enable_vault_eso,
        enable_cnpg,
        runner_temp,
        output_dir,
        github_env,
    )
    inputs = resolve_render_inputs(raw_inputs)
    tfvars = build_render_tfvars(inputs)

    try:
        manifests = render_manifests(inputs, tfvars)
        _handle_manifest_output(inputs, manifests)
    except (InfraK8sError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    else:
        return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(app())
