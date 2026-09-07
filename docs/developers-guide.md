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

## Gate recipes

`SHELL := bash` is the only shell setting in the `Makefile`: there is no
`.ONESHELL` and no `-e` in `.SHELLFLAGS`. Make hands each recipe line to its
own shell and inspects that shell's exit status, so a line that chains
commands with `;` reports only the last command's status and discards every
earlier failure.

That is not hypothetical. Before this rule existed, adding a workflow file
with trailing whitespace made yamllint exit 1 inside `make lint-actions`,
which then ran actionlint, and Make saw actionlint's clean status:

```console
$ yamllint .github/workflows/zz-repro.yml; echo "rc=$?"
  5:9  error  trailing spaces  (trailing-spaces)
rc=1
$ make lint-actions; echo "rc=$?"
  5:9  error  trailing spaces  (trailing-spaces)
rc=0
```

### The rule

Every gate recipe line is a single command. Any multi-command gate logic
lives in a Python script under `scripts/` written to the
[scripting standards](scripting-standards.md), and the recipe invokes that
script with `$(UV) run`. That covers a `;` chain, a loop, a conditional and a
pipeline. `|| exit 1` on each link is an interim guard, not a fix.

A pipeline hides a failure the same way: without `pipefail`, bash reports only
the last stage's status, so `helm template chart | yamllint -` passed on a
chart that failed to render.

The scripts share `scripts/_gate_runner.py`, which runs tools in sequence,
stops at the first unexpected exit status and names the tool that failed.
Standard input is closed unless a step supplies it, so a gate cannot hang on
a tool that reads a terminal, and `capture_tool` replaces shell pipelines
where one tool's output feeds the next.

| Script                   | Recipes it owns                              |
| ------------------------ | -------------------------------------------- |
| `lint_actions.py`        | `lint-actions`                               |
| `lint_helm_manifests.py` | `yamllint`                                   |
| `run_bun_tool.py`        | `lint`, `check-fmt`, `markdownlint`          |
| `tofu_example_gate.py`   | the `*-test` validate and plan steps         |
| `tofu_plan_policy.py`    | the `*-policy` plan, export and conftest run |
| `check_spelling.py`      | the typos step of `spelling`                 |

`scripts/_tofu_modules.py` holds each module's example path, gate variable,
required companion variables and `-var` assignments, so one script serves
every module. A gate stays opt-in: when the module's kubeconfig variable is
unset the script reports a skip, exactly as the recipes did. The variables are
`export`ed in the `Makefile` so a `make <target> VAR=value` override still
reaches the script.

### The contract

`scripts/tests/test_makefile_gate_contract.py` reads every `.PHONY` target's
recipe through `make --dry-run`, which yields the fully expanded text the
shell receives, and asserts each line is a single command or enables `errexit`
before it chains. A pipeline additionally needs `pipefail` to count as
guarded. Semicolons inside quotes, a `$(...)` substitution, a subshell or a
`{ ...; }` group are not separators, and `&&` or `||` lists already stop at
the first failure. A `.PHONY` list held in a variable is expanded, and an
unreadable reference is an error rather than a silently smaller contract.

To prove the contract still bites, put a chain back into a recipe and run the
test; it fails for that target, for every target that reaches it, and for the
whole-Makefile check. The suite carries the same mutation as a test of its
own, against a temporary Makefile. A property test generates commands whose
separators are hidden in quoting, escaping, substitutions, subshells and brace
groups, with the real offsets known by construction.

The contract resolves GNU Make before it measures anything, preferring
`gmake`, and fails when `--version` does not report GNU Make. One shell per
recipe line, `.ONESHELL` and `--dry-run` expansion are GNU Make behaviours, so
another make would expand differently and the measurement would mean nothing.
The expected command is compared in full rather than by prefix, because a
prefix match would certify a recipe whose invocation had been neutralized with
a trailing option.

A second contract, `test_makefile_gate_environment.py`, derives the gate
variable names from the module registry and asserts the Makefile exports each
one, then runs Make for real and reads the value back out of a child process.
Without the export, `make <target> VAR=value` would be silently ignored and
the gate would report a skip.

`test_gate_scripts_end_to_end.py` starts each script in a subprocess against a
search path holding only fake tools, so the exit code and the diagnostic Make
depends on are tested at the process boundary rather than through an
in-process call.

A recipe line may also disown its exit status with a leading `-`, which is
Make's own `|| true`. `make --dry-run` strips that prefix before printing, so
the contract reads the recipe text for it rather than the expansion.

### CI runs the gates

Converting the recipes only helps while the workflow still runs them, and a
contract that searched a step's `run` value for the command would pass on a
step that never executes. `test_workflow_gate_contract.py` requires the whole
shape instead: the job exists, some step's entire `run` is the gate command,
and neither the job nor that step carries a condition. A condition is detected
by the presence of the `if` key, never by its value, because `if: false`
parses to a boolean and a plausible condition such as a push-only one is not
falsy at all. Nine mutations are proved to fail the contract, including a
condition on the step and on the job, a wrapper, a `|| true` suffix, a
mistyped command and a removed `pull_request` trigger.

`.SHELLFLAGS := -eo pipefail -c` is deliberately absent. It would make a
forbidden recipe shape work rather than removing it, weakening the contract,
and it would change the meaning of every existing recipe line at once. The
mechanism this repository relies on is one command per line.

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
