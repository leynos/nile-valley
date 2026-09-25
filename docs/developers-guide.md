# Developers' guide

This guide records repository-wide development practices. More specialized
guidance remains in the documents linked from the
[documentation index](contents.md).

## Spelling policy

Run `make spelling` to enforce en-GB-oxendict spelling in maintained Markdown
prose. The single gate command is
[typos-config-builder](https://github.com/leynos/typos-config-builder), pinned
by `TYPOS_CONFIG_BUILDER_VERSION` in the `Makefile`. It regenerates
`typos.toml` from the live shared dictionary and the repository overlay on
every run, runs the pinned Typos binary over the tracked Markdown, and enforces
the shared prohibited-phrase policy.

`typos.toml` is therefore a generated artefact. It is never edited by hand and
never drift-checked in CI, because the shared dictionary is the authority and a
dictionary change would otherwise fail every consumer's pipeline. Narrow
repository exceptions belong in `typos.local.toml`.

## CodeScene rule overrides

This repository declares no CodeScene rule overrides. The file that held them,
`.codescene/code-health-rules.json`, was removed because its one rule set had
never applied: it used a top-level `rules` map with `threshold-by-pattern`,
which CodeScene rejects, and its glob named Rust sources in a repository that
contains none. Removing it changed no verdict, because CodeScene had never read
it.

The failure mode is worth knowing before writing a replacement. A rule set the
tool cannot read is skipped, the verdicts carry on without the override, and
the only sign is a line on standard error that a passing run buries. The
diagnostic blames JSON syntax, which sends the reader looking for a missing
comma, when the real cause is that hyphenated keys read as namespaced keywords.

To add an override, use the schema `cs docs code-health-rules-template` prints:
a top-level `rule_sets` array, each entry naming a `matching_content_path` and
justifying itself in `matching_content_path_doc`, and each rule named in prose
with a `weight` between 0.0, which disables it, and 1.0, which is the default.
Validate it before pushing:

```bash
cs rules-config validate
```

That is a local check and stays one. The CodeScene command-line tool does not
belong in CI or in a Makefile target: the GitHub integration reads the same
rule set, so running the tool as well would duplicate the check under a licence
the runners do not need. With no overrides declared the command reports "No
configuration file found" and exits non-zero, which is the expected state here
rather than a fault.

`scripts/tests/test_codescene_rules.py` is a schema test, not a substitute for
either. It asserts the documented shape rather than merely that the file is
JSON, requires every rule set to justify itself, requires every glob to match
at least one file, since a glob left behind by a rename or a copy is an
exemption that quietly stops applying, and checks the type of every field a
rule set declares before anything reads it because a wrong type does not
announce itself downstream: a `rules` value of `""` iterates zero times and so
satisfies every rule check.

`thresholds` is the field that repays the most care. It is an array of
`{name, value}` objects rather than a mapping, and given a mapping the
CodeScene command-line tool does not report a schema problem: it exits with an
unhandled exception and asks for the stack trace to be sent to support. The
value must be a positive number; the tool refuses zero, a negative and a
non-numeric string, while accepting a fraction and coercing a numeric string.
An entry still carrying the template's `"-"` placeholder overrides nothing, so
the contract rejects it as residue.

Beyond the named shapes, the checks are stated as properties over generated
documents: any document built to the schema passes every check, and each
single-field mutation of one fails the check that owns that field.

Those checks run against the committed `.codescene/code-health-rules.json`
whenever there is one, and skip while there is none. They are not something to
reinstate later: a rule file added without them would be validated by nothing,
which is how the removed one survived.

## Gate recipes

`SHELL := bash` is the only shell setting in the `Makefile`: there is no
`.ONESHELL` and no `-e` in `.SHELLFLAGS`. Make hands each recipe line to its
own shell and inspects that shell's exit status, so a line that chains commands
with `;` reports only the last command's status and discards every earlier
failure.

That is not hypothetical. Before this rule existed, adding a workflow file with
trailing whitespace made yamllint exit 1 inside `make lint-actions`, which then
ran actionlint, and Make saw actionlint's clean status:

```console
$ yamllint .github/workflows/zz-repro.yml; echo "rc=$?"
  5:9  error  trailing spaces  (trailing-spaces)
rc=1
$ make lint-actions; echo "rc=$?"
  5:9  error  trailing spaces  (trailing-spaces)
rc=0
```

### The rule

Every gate recipe line is a single command. Any multi-command gate logic lives
in a Python script under `scripts/` written to the
[scripting standards](scripting-standards.md), and the recipe invokes that
script with `$(UV) run`. That covers a `;` chain, a loop, a conditional, and a
pipeline. `|| exit 1` on each link is an interim guard, not a fix.

A pipeline hides a failure the same way: without `pipefail`, bash reports only
the last stage's status, so `helm template chart | yamllint -` passed on a
chart that failed to render.

The scripts share `scripts/_gate_runner.py`, which runs tools in sequence,
stops at the first unexpected exit status and names the tool that failed.
Standard input is closed unless a step supplies it, so a gate cannot hang on a
tool that reads a terminal.

Where one tool's output feeds the next, the shape depends on what the output
is. A generated artefact goes to a file: `write_tool_output` redirects the
tool's standard output into it, and a consumer reads it back through a run's
`stdin_path`. That is how an OpenTofu plan reaches conftest as JSON and how a
rendered chart reaches yamllint, so the size of a plan or a chart does not
become the gate's memory footprint. `capture_tool` holds output in memory and
is reserved for output bounded by construction, such as the list of tracked
files a gate checks.

The gate scripts read the environment once, at the command line, and pass the
mapping down. Nothing below that boundary consults `os.environ`, so the
variables a decision was made from are the ones the caller can see, and the
module registry is a read-only mapping for the same reason.

| Script                   | Recipes it owns                                  |
| ------------------------ | ------------------------------------------------ |
| `lint_actions.py`        | `lint-actions`                                   |
| `lint_helm_manifests.py` | `yamllint`                                       |
| `run_bun_tool.py`        | `lint`, `typecheck`, `check-fmt`, `markdownlint` |
| `tofu_example_gate.py`   | the `*-test` validate and plan steps             |
| `tofu_plan_policy.py`    | the `*-policy` plan, export and conftest run     |

`scripts/_tofu_modules.py` holds each module's example path, gate variable,
required companion variables and `-var` assignments, so one script serves every
module. A gate stays opt-in: when the module's kubeconfig variable is unset the
script reports a skip, exactly as the recipes did. The variables are `export`ed
in the `Makefile` so a `make <target> VAR=value` override still reaches the
script.

### The contract

`scripts/tests/test_makefile_gate_contract.py` reads every `.PHONY` target's
recipe through `make --dry-run`, which yields the fully expanded text the shell
receives, and asserts each line is a single command or enables `errexit` before
it chains. A pipeline additionally needs `pipefail` to count as guarded.
Semicolons inside quotes, a `$(...)` substitution, a subshell or a `{ ...; }`
group are not separators. An `&&` list already stops at the first failure,
whereas a `||` list runs its right-hand command only after a failure, and a
succeeding right-hand command masks that failure as `|| true` does. A `.PHONY`
list held in a variable is expanded, and an unreadable reference is an error
rather than a silently smaller contract.

To prove the contract still bites, put a chain back into a recipe and run the
test; it fails for that target, for every target that reaches it, and for the
whole-Makefile check. The suite carries the same mutation as a test of its own,
against a temporary Makefile. A property test generates commands whose
separators are hidden in quoting, escaping, substitutions, subshells and brace
groups, with the real offsets known by construction. It uses Hypothesis, which
the `scripts-test` recipe installs through its `uv run --with hypothesis`
invocation alongside the other test dependencies.

The contract resolves GNU Make before it measures anything, preferring `gmake`,
and fails when `--version` does not report GNU Make. One shell per recipe line,
`.ONESHELL` and `--dry-run` expansion are GNU Make behaviours, so another make
would expand differently and the measurement would mean nothing. The expected
command is compared in full rather than by prefix, because a prefix match would
certify a recipe whose invocation had been neutralized with a trailing option.

A second contract, `test_makefile_gate_environment.py`, derives the gate
variable names from the module registry and asserts the Makefile exports each
one, then runs Make for real and reads the value back out of a child process.
Without the export, `make <target> VAR=value` would be silently ignored and the
gate would report a skip.

`test_gate_scripts_end_to_end.py` starts each script in a subprocess against a
search path holding only fake tools, so the exit code and the diagnostic Make
depends on are tested at the process boundary rather than through an in-process
call.

A recipe line may also disown its exit status with a leading `-`, which is
Make's own `|| true`. `make --dry-run` strips that prefix before printing, so
the contract reads the recipe text for it rather than the expansion.

### CI runs the gates

Converting the recipes only helps while the workflow still runs them, and a
contract that searched a step's `run` value for the command would pass on a
step that never executes. `test_workflow_gate_contract.py` requires the whole
shape instead: the job exists, some step's entire `run` is the gate command,
and neither the job nor that step carries a condition. A condition is detected
by the presence of the `if` key, never by its value, because `if: false` parses
to a boolean and a plausible condition such as a push-only one is not falsy at
all. Ten mutations are proved to fail the contract, for each of the two newest
gates: a condition on the step in both its boolean and its string spelling, a
condition on the job, a push-only condition on either, a wrapper that leaves
the command unreachable, a `|| true` suffix, a mistyped command, a removed step
and a removed `pull_request` trigger.

The same workflow is read a second time by `act`, in
`test_workflow_act_integration.py`. That is not a duplicate of the contract
above: a YAML reader sees a malformed `${{ }}` expression as an ordinary
string, and a misspelled job key as a field it does not recognize but does not
reject, while the runner's own reader rejects both. `act` is not installed in
CI, so those checks are skipped there and the module keeps a set of premise
tests that are not: they assert, without the binary, that each sample `act` is
fed is parseable and malformed and that each workflow is a mapping with jobs.
Skipping the premises too would leave the module asserting nothing in CI, and a
sample that merely failed to parse would make the `act` checks pass for a
reason unrelated to what they claim to test. `act --list` performs that reading
without scheduling a container, so it costs about a second and needs no daemon;
the containerized run is left to the ladder described in
[Local validation of GitHub Actions with act and pytest](local-validation-of-github-actions-with-act-and-pytest.md).

`.SHELLFLAGS := -eo pipefail -c` is deliberately absent. It would make a
forbidden recipe shape work rather than removing it, weakening the contract,
and it would change the meaning of every existing recipe line at once. The
mechanism this repository relies on is one command per line.

## The documented-example gate

Repository policy is that a function's documentation carries an example showing
use and outcome. An example that has drifted from the code is worse than none,
so the gate discovers every eligible module under `scripts` and runs the
examples of every one it can import, as part of `make test`.

The gate is five modules under `scripts/tests`, because no code file here may
exceed 400 lines. `gate_script_docs_support.py` holds the walk, the exemption
list and the execution boundary, and `gate_script_docs_path_support.py` holds
the rules that read a source for the absolute paths its examples name. The
questions are asked in `test_gate_script_docs.py` for coverage,
`test_gate_script_docs_host_writes.py` for what a run does to the filesystem,
and `test_gate_script_docs_rules.py` for the proof that those rules bite.

The distinction is not pedantry. A module that cannot be imported has no
examples run at all, and saying otherwise would describe a gate stronger than
the one that exists, so a run reports `not-importable` as its own verdict
rather than as a stale example. No module is in that state today: the three
that were are the spelling rollout's, deleted when the repository adopted
`typos-config-builder`.

The module list is walked rather than written down. The handwritten list it
replaces named eleven modules while thirty-four carried examples, so 199 of 269
example lines were never run, and adding a module with a stale example changed
nothing a reader would notice.

### What the walk reaches

Every `.py` under `scripts`, except `conftest.py`, `__init__.py`, and anything
under `scripts/tests`. The suite is pytest's to import: a second import under a
dotted name re-runs every module-level statement against a different module
object, and three modules there import `cmd_mox` at module level while
`conftest` registers its plugin only when the package is present.

`scripts/tests` holds two kinds of file, and excluding the directory treated
them as one. A test module is pytest's. A support module, named `*_support.py`,
is an ordinary library the test modules import, nothing else claims it, and its
examples are as much documentation as any script's. The hand list this walk
replaced named three support modules outright and ran them; the exclusion
dropped all of them, and said their examples were covered by
`--doctest-modules` on the suite's own invocation. No pytest invocation in this
repository passes that flag, and there is no configuration file to carry it, so
twenty-eight example lines stopped running and the gate reported nothing. The
support modules are discovered by their suffix and checked through the same
boundary as everything else, and a separate assertion refuses an empty
discovery, because a glob matching nothing would otherwise satisfy a
parametrized test by having no cases.

Discovery is asserted against an independently built set rather than against
itself, and the walk is checked to be neither empty nor missing a named module,
so a filter that excluded everything would not pass.

### Where the examples run

The gate creates a temporary directory, runs the examples inside it, and throws
it away. The process is returned to where it started. Documented examples are
ordinary code and some of them write: two in the manifest writer named absolute
paths under `/tmp` and created them on every run of this suite. Those two are
repaired at the source to use a temporary directory and to assert what they
produce, which retired that module's exemption the same day. The isolation
stays because the next careless example is not hypothetical, and it is
asserted: a relative write from inside the boundary lands in the scratch
directory and the repository root is unchanged afterwards.

The environment is restored with the working directory, and for the same
reason. The output publisher's example assigns `SPACES_ACCESS_KEY`, and until
the restore landed it stayed assigned for the rest of the pytest session: a
variable carrying a secret's name, set by a gate, visible to every test that
ran afterwards. That the example is stale is no protection, because `doctest`
runs each example up to the point it fails and carries on to the next, so a
broken example's effects land anyway. The environment is put back wholesale
rather than by removing what appeared, since an example can delete a variable
as easily as add one. Repairing such an example is separate work, tracked in
[#103](https://github.com/leynos/nile-valley/issues/103); containing it is the
boundary's job.

### The exemption list

It shrinks and never grows by accident: a module not named in it is checked
from the moment it exists.

`KNOWN_STALE_EXAMPLES` holds modules whose examples did not hold when the walk
replaced the hand list. `test_a_listed_module_is_still_stale` fails when a
listed module starts passing, so a repair cannot leave its entry behind, and
`test_every_exemption_names_a_discovered_module` fails when an entry names
something the walk no longer finds, so a deleted module cannot keep one. The
list is tracked in [#103](https://github.com/leynos/nile-valley/issues/103).

An entry must be stale rather than merely unreadable, which is why the outcome
of a run is one of three named verdicts and the stale-list test asserts `stale`
specifically. Collapsing an import failure into "stale examples" is what let an
exemption for a deleted module satisfy the shrink-only rule forever. The
checked set is separately asserted to be larger than the exempted one, so the
list cannot grow until the gate has nothing left to do.

## The type check

`scripts/install-mermaid-browser.mjs` is the one JavaScript file this
repository ships, so it is the only one the compiler sees. `make typecheck`
checks it with JavaScript checking enabled and emits nothing:

```console
$ make typecheck
$ uv run scripts/run_bun_tool.py --tool tsc --package typescript@5.9.2 -- \
    --allowJs --checkJs --noEmit --target ES2022 \
    --module NodeNext --moduleResolution NodeNext \
    scripts/install-mermaid-browser.mjs
```

`--allowJs` is what admits a `.mjs` file at all, and `--checkJs` is what makes
the compiler report on it rather than merely parse it. `--noEmit` keeps the
target read-only: it is a check, not a build, so the file is never rewritten
and no `.js` output lands beside the source. The script runs only under Node's
ES module resolution, and it writes through `process`, so `--target ES2022`,
`--module NodeNext` and `--moduleResolution NodeNext` are the settings its
imports and globals are checked against.

The TypeScript version is pinned as `TYPESCRIPT_VERSION ?= 5.9.2` beside the
other tool versions at the top of the `Makefile`, so it can be overridden for a
one-off run the same way the rest can:

```console
make typecheck TYPESCRIPT_VERSION=5.9.1
```

The target is a member of `all` (`check-fmt lint typecheck test spelling`) and
runs in CI as the `Type check` step, after `Lint`. Like the other gates it is
reachable on its own, which is the loop to use while editing the script.

The `Makefile` does not invoke `tsc` directly. It runs
`$(UV) run scripts/run_bun_tool.py`, which prefers a `tsc` already on `PATH` —
so a warm CI cache is used rather than a download — and otherwise obtains the
pinned package through Bun's `x` command:

```console
uv run scripts/run_bun_tool.py --tool tsc --package typescript@5.9.2 -- <args>
```

`--` separates the runner's own options from the arguments passed through to
`tsc`; `--package` is the version-pinned npm spec Bun fetches when the tool is
absent. A non-zero `tsc` status reaches Make unchanged, so a type error fails
the gate with the compiler's own diagnostic.

`node_modules` has to be installed first. The script imports `node:fs`,
`node:url`, the `puppeteer` package and a deep path inside it, so checking it
outside an installed tree reports `Cannot find module 'puppeteer'` and
`Cannot find name 'process'` rather than a type error of its own. Run
`make deps` before `make typecheck`; the `install-dependencies` step already
orders them that way in CI.

## The roadmap heading grammar

`docs/ephemeral-previews-roadmap.md` is read by `mapsplice`, which accepts two
heading forms and rejects everything else inside the roadmap body:

```markdown
## 1. Application delivery and GitOps strategy (To do)

### 2.1. DigitalOcean Kubernetes cluster
```

A phase is written `## N. Title` and a step `### N.M. Title`: a bare integer, a
literal dot, a space, then the title. A status suffix such as `(To do)` is part
of the title and is accepted. The step's `N` must equal the number of the phase
that encloses it, so `### 1.1.` under `## 2.` is rejected with "step heading
`1.1` does not belong to phase `2`".

The forms this document used before it was aligned with the grammar are
rejected outright: `## Phase 1: Title` for a phase, and `### 1.1: Title` or
`### 1.1 Title` for a step. A level-four heading is rejected too, and a
non-heading opening makes the tool report "must start with a phase heading".

Two things the tool does *not* check, which the tests therefore check
themselves. Numbering need not be sequential or gap-free -- a document may run
`## 1.` then `## 3.`, and steps `1.1.` then `1.3.` -- so the expected sequence
is asserted separately. And a step is checked against its number, not its
position, so a step may sit under the wrong phase as long as its number agrees
with one that exists.

`mapsplice` mutates a document rather than validating one, so it has no "is
this file well formed" verb. The tests confirm a document by appending its own
phase-onward body to a copy of it: the tool accepts the result only if both the
fragment and the target satisfy the grammar, which is the same confirmation the
original alignment used. `test_roadmap_grammar.py` also feeds each accepted and
each rejected form to the tool, so the patterns cannot drift from the tool's
real behaviour in either direction.

The support is split by whether the tool is needed.
`roadmap_grammar_support.py` holds the patterns and the readers built on them,
reads text, and installs nothing, so the contract it backs runs wherever the
suite runs. `mapsplice_support.py` runs the binary and is imported only by the
tests that are skipped without it; its documented examples carry
`# doctest: +SKIP` for the same reason, since the example gate executes them on
every machine.

## Continuous integration

The `ci` workflow runs a single `build` job, on `ubicloud-standard-2` for this
repository's own pull requests and pushes and on `ubuntu-latest` for a pull
request from a fork. It is the only repository-owned build and test job. Every
other job is scheduled, API-bound, or release orchestration and stays on a
GitHub-hosted runner.

| Workflow and job                           | Runner                           | Fork fallback   | Timeout    |
| ------------------------------------------ | -------------------------------- | --------------- | ---------- |
| `ci.yml:build`                             | `ubicloud-standard-2`            | `ubuntu-latest` | 30 minutes |
| `delayed-pr-comment.yml:delay_and_comment` | `ubuntu-latest`                  | not applicable  | none       |
| `dependabot-automerge.yml:automerge`       | reusable workflow, declares none | not applicable  | none       |

The repository uses one distinct Ubicloud label, and `.github/actionlint.yaml`
registers exactly that one label.
`test_self_hosted_labels_are_registered_with_actionlint` asserts the two sets
equal in both directions, so moving the job to another size fails the contract
until the registry moves with it, and a registered label that no job uses fails
it too.

### Why two vCPUs

The step that dominates the job cannot use a second core. `make test` is a
single `pytest scripts/tests` invocation: there is no xdist plugin among the
`uv run --with` arguments, no `addopts` anywhere in the repository, and no
`multiprocessing`, thread pool or `make -j` in `scripts/`. Over five green runs
on `ubicloud-standard-8` it was 70 to 79 seconds of a job lasting 130 to 186
seconds, so it is nearly half to over half the wall clock on its own. Pinned to
two cores locally the whole suite finished in 93 seconds against 101 seconds
unpinned, which is noise: it does not scale, so seven of the eight cores sat
idle through it at four times the two-vCPU rate.

One step does scale, and it was measured rather than assumed. `make lint-infra`
ends in `checkov -d infra`, which forks across files. Pinned locally it took 56
seconds on two cores against 38 on eight, an 18-second difference. That local
figure does not carry over directly, because the workload it measures is the
whole of `checkov` on a loaded 32-core host, while the `Lint` step in CI is 21
to 36 seconds in total.

The move was therefore checked against a real run rather than projected. The
first `ubicloud-standard-2` run of this job finished in 132 seconds, with 74
seconds in `Tests` and 23 seconds in `Lint`. Both sit inside the standard-8
bands above, so the `checkov` difference did not show at the job level at all.

`test_the_gate_is_sized_to_the_label_the_measurements_justify` asserts the
Ubicloud arm by name. The registry contract cannot do that job: it only
requires the workflow and `.github/actionlint.yaml` to agree, so setting both
files back to `ubicloud-standard-8` satisfies it exactly and quadruples the
rate with nothing to notice. Naming the label makes a change to the size
deliberate enough to edit the contract and re-read this section.

Revisit the size only if a step that genuinely scales with cores grows to
dominate the wall clock. Measure it pinned, then confirm against a run on the
label you propose, the way these figures were obtained.

### When the gate runs

On a pull request, and on a push to `main`. The trunk trigger is not
decoration: every cache save step is guarded on `refs/heads/main`, so without
an event that produces that ref the guard is never true on an automatic run and
no cache is ever written. See the cache ownership section below.

A `workflow_dispatch` is declared as well, and does not count towards that
guarantee. It can be aimed at trunk, so it satisfies the guard in principle,
but a cache written only when somebody remembers to press a button is written
never.

### Cancelling superseded pull-request runs

A push to a pull request starts a fresh run of the gate, and the run already in
flight is answering a question about a commit nobody will merge. Left alone it
holds the runner until it finishes, so the branch pays twice for one answer.
`ci.yml` therefore declares:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

When there is no pull request the group falls back to `github.run_id`, so two
pushes to `main` or two dispatches never share a group. A shared ref group
would let a third run replace a still-pending second one, and that commit would
never get CI; two trunk runs overlapping is the cheaper risk, because
compiler-cache writes are content-addressed and a cache save of an existing key
is refused harmlessly (estate rule "PR-lane concurrency fallback").

The group keys on the pull request, so one branch never cancels another's run,
and a group built from `github.run_id` alone would match no predecessor and
cancel nothing. Cancellation is conditioned on the event rather than set to a
literal `true`, because the push to `main` is the single cache writer described
above: a merge landing while the previous trunk run saves its caches would
otherwise kill that save. Each push to `main` gets its own group, so none is
cancelled or replaced. `dependabot-automerge.yml` runs on `pull_request_target`
and merges, so it is out of scope: cancelling a merge mid-flight is a hazard
with no minutes to win.

`scripts/tests/test_workflow_concurrency.py` holds the rule for every workflow
declaring a `pull_request` trigger. It reads `on:` as a mapping, a list or a
bare name under both the quoted key and PyYAML's boolean `True`, and refuses a
workflow declaring both. It keeps a floor of `ci.yml` so discovery cannot empty
into a vacuous pass, and requires a group that, rendered by
`pr_concurrency_groups.py`, keeps two pushes to one pull request together and
keeps apart that pull request, a fork's pull request from a branch of the same
name, two pushes to `main`, and two dispatches of another branch; and that uses
`github.run_id` only as the fallback behind the pull-request number. A
`github.ref` or `github.base_ref` fallback, a `github.head_ref`, `github.sha` or
`github.run_id`-only group, the run identifier ahead of the number, or a
constant group fails, and an expression the renderer does not model is refused
rather than guessed at. It also requires exactly the event-conditioned
`cancel-in-progress` expression. No two pull-request workflows may render the
same group for one pull request, since whichever started last would cancel the
others; each is rendered under its own name, and the groups are compared
casefolded because GitHub treats group names case-insensitively. Because
`ci.yml` is the only pull-request workflow today, each group is also rendered
under two synthetic workflow names and must differ, so a group without
`github.workflow` fails now rather than when a second workflow lands. It reads
the files through a loader that refuses a duplicated mapping key, because
PyYAML keeps the last of two `concurrency:` blocks and says nothing. Each
clause was proved by mutation: the cancel line removed, a literal `true`, a
`ref` fallback, the run identifier ahead of the number, a constant group, a
`head_ref` group, a `format()` group, the block removed, the trigger renamed to
`pull_request_target`, a duplicated block, an unquoted `on:` beside the quoted
one, the `github.workflow` prefix dropped, and the casefold removed from the
comparison each fail it.

### Placement rule

Delayed pull-request comments, scheduled work, metadata and label automation,
and release orchestration run on GitHub-hosted `ubuntu-latest`. Only the
`build` job may use a self-hosted label, and every intentional label is
registered in `.github/actionlint.yaml`.

`build` selects its runner by expression rather than by a bare label:

```yaml
runs-on: >-
  ${{ github.event.pull_request.head.repo.fork
  && 'ubuntu-latest' || 'ubicloud-standard-2' }}
```

A pull request from a fork cannot obtain an Ubicloud runner, so a bare Ubicloud
label would leave the only required check unable to start and the pull request
waiting on a job that is never scheduled. Keep the continuation at the same
indent: a more-indented continuation in a folded scalar keeps its line break,
which puts a newline inside the expression. GitHub evaluates the broken value
anyway, so a green run is no evidence that it is written correctly.

The contracts are split across three modules, because no code file here may
exceed 400 lines. `scripts/tests/test_workflow_contracts.py` asks what the jobs
install, pin and cache; `scripts/tests/test_workflow_placement_contracts.py`
asks which runner a job lands on; and
`scripts/tests/test_workflow_filter_contracts.py` asks which branches an
event's filters admit, which is what decides whether a trunk-guarded step has
anything that can reach it.

The placement module asserts, among other things, that no `runs-on` parses with
a line break in it, and that the fork arm is the hosted one: the two arms are
read by position, because an expression that sends a fork to the paid runner
names exactly the same two labels as one that does not. It asserts the fork
field as a bounded token rather than as a substring, since `head.repo.forked`
names no field GitHub defines, evaluates false, and sends every fork to the
runner a fork cannot obtain. An expression the reader cannot follow, such as
`${{ matrix.runner }}`, yields a sentinel label rather than nothing: nothing
reads as "declares no runner", which every placement contract skips, so an
unreadable declaration would pass them all by being unreadable.

The filter module drives `scripts/tests/workflow_filter_support.py`, which
reads GitHub's own glob rather than a near neighbour. `*` stops at a separator
and `**` crosses one; `?` and `+` bind to the character before them and stand
for zero-or-one and one-or-more of it; `[]` is a class of alphanumerics and
ranges. Patterns within one key are evaluated in order, so a later `!` entry
excludes what an earlier entry admitted and a later positive entry admits it
again. Each of those was wrong at some point, and each error reads a filter as
covering branches it does not, which is how a reachability answer comes out
wrong while every test stays green.

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
single writer for every key, and the workflow's `push` trigger on `main` is
what makes that guard reachable. The two belong together: the guard was in
place for months while no automatic event could produce that ref, so every save
was skipped on every run, the repository held no cache entries at all, and each
restore found nothing. A guard on a step that nothing can reach is worse than
no guard, because it reads as a mechanism.

`test_every_trunk_guarded_step_has_an_event_that_reaches_it` is what keeps the
two together, for any workflow and not only this one.
