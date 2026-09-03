# Developers' guide

This guide records repository-wide development practices. More specialized
guidance remains in the documents linked from the
[documentation index](contents.md).

## Spelling policy

Run `make spelling` to enforce en-GB-oxendict spelling in maintained Markdown
prose. The generated `typos.toml` starts from the shared estate dictionary,
refreshes its untracked local cache only when the authority is newer, and then
applies the narrow repository policy in `typos.local.toml`. Edit the local
policy and regenerate the configuration rather than changing generated entries
by hand.

`scripts/typos_rollout_http.py` owns shared-cache freshness, HTTPS transport
security and persistence coordination. Only `scripts/typos_rollout.py` may
compose it with dictionary validation; infrastructure scripts must not reuse
these spelling-policy internals.

## Continuous integration

The `ci` workflow runs a single `build` job on `ubicloud-standard-8`. It is the
only repository-owned build and test job. Every other job is scheduled,
API-bound, or release orchestration and stays on a GitHub-hosted runner.

### Placement rule

Delayed pull-request comments, scheduled work, metadata and label automation,
and release orchestration run on GitHub-hosted `ubuntu-latest`. Only the
`build` job may use a self-hosted label, and every intentional label is
registered in `.github/actionlint.yaml`. The workflow contract tests in
`scripts/tests/test_workflow_contracts.py` enforce the rule.

### Tool installation

CI installs prebuilt, version-pinned binaries and never compiles a tool from
source. Every pin lives in the `env:` block at the top of
`.github/workflows/ci.yml`, so a pin change invalidates the cache generation
that holds the old binary.

| Tool             | Source                                  | Verification                                         |
| ---------------- | --------------------------------------- | ---------------------------------------------------- |
| Nixie and Merman | `leynos/shared-actions` `install-nixie` | Pinned uv release; checksum-pinned Merman archive    |
| Bun              | `oven-sh/setup-bun`                     | Pinned action commit and Bun version                 |
| uv               | `astral-sh/setup-uv`                    | Pinned action commit and uv version                  |
| Helm             | `azure/setup-helm`                      | Pinned action commit and Helm version                |
| TFLint           | `terraform-linters/setup-tflint`        | Pinned action commit and TFLint version              |
| yamllint, mbake  | `uv tool install`                       | Pinned versions; version probe guards the warm cache |
| action-validator | `scripts/install_action_validator.py`   | SHA256 from the release metadata                     |
| actionlint       | Release tarball                         | SHA256 pinned in the workflow                        |
| checkmake        | Release binary                          | SHA256 pinned in the workflow                        |

Merman previously came from `cargo install merman-cli`, which also required a
Rust toolchain that nothing else in this repository uses. Both are gone.
`actionlint` and `checkmake` previously came from `go install`; the Go
toolchain that served only those two source builds is gone with them. When a
job starts running the OpenTofu module Go suites, reinstate `actions/setup-go`
with an exact version and let its own cache own the Go module and build trees.

### Cache ownership

Each mutable path has exactly one owner and one explainable key. Every key
carries the `v1` generation, `runner.os`, `runner.arch`, and
`runner.environment`, so a Ubicloud archive can never be restored onto a
GitHub-hosted runner. Caches use `actions/cache/restore` and
`actions/cache/save` pinned to v6.1.0.

| Owner step                      | Paths                                                                 | Key inputs beyond the common prefix     |
| ------------------------------- | --------------------------------------------------------------------- | --------------------------------------- |
| Restore tooling cache           | `~/.cache/uv`, `~/.local/share/uv`, `~/.local/bin`, `~/.cache/merman` | Digest of every tool pin                |
| Restore workspace uv cache      | `.uv-cache`, `.uv-tools`                                              | `Makefile` hash                         |
| Restore Bun install cache       | `~/.bun/install/cache`                                                | Bun version and `bun.lock` hash         |
| Restore Puppeteer browser cache | `~/.cache/puppeteer`                                                  | `bun.lock` hash                         |
| Restore TFLint plugin cache     | `~/.tflint.d/plugins`                                                 | TFLint version and `.tflint.hcl` hashes |

The three uv layers are cached together because restoring only the tool
environments makes `uv tool install` report success while the shim is absent.
`~/.local/bin` holds both the uv shims and the release binaries, so one step
owns it. `astral-sh/setup-uv` sets `enable-cache: false` for the same reason:
two owners for `~/.cache/uv` is a policy failure.

`node_modules` is deliberately not archived. A frozen install from a warm
download cache is cheaper than restoring the installed tree, and no build
product is cached at all.

Pull requests restore the trusted generation but never publish one. Every save
step is guarded by `github.ref == 'refs/heads/main'`, which makes `main` the
single writer for every key. The workflow currently has no `push` trigger, so
the first trusted generation must be published by a `workflow_dispatch` run on
`main`, or by adding a trunk trigger when the runner migration lands.
