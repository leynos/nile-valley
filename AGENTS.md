# Assistant Instructions

## Code Style and Structure

- **Code is for humans.** Write your code with clarity and empathy—assume a
  tired teammate will need to debug it at 3 a.m.
- **Comment *why*, not *what*.** Explain assumptions, edge cases, trade-offs, or
  complexity. Don't echo the obvious.
- **Clarity over cleverness.** Be concise, but favour explicit over terse or
  obscure idioms. Prefer code that's easy to follow.
- **Use functions and composition.** Avoid repetition by extracting reusable
  logic. Prefer generators or comprehensions, and declarative code to
  imperative repetition when readable.
- **Small, meaningful functions.** Functions must be small, clear in purpose,
  single responsibility, and obey command/query segregation.
- **Clear commit messages.** Commit messages should be descriptive, explaining
  what was changed and why.
- **Name things precisely.** Use clear, descriptive variable and function names.
  For booleans, prefer names with `is`, `has`, or `should`.
- **Structure logically.** Each file should encapsulate a coherent module. Group
  related code (e.g., models + utilities + fixtures) close together.
- **Group by feature, not layer.** Colocate views, logic, fixtures, and helpers
  related to a domain concept rather than splitting by type.
- **Use consistent spelling and grammar.** Comments must use en-GB-oxendict
  ("-ize" / "-yse" / "-our") spelling and grammar, with the exception of
  references to external APIs.
- **Illustrate with clear examples.** Function documentation must include clear
  examples demonstrating the usage and outcome of the function. Test
  documentation should omit examples where the example serves only to reiterate
  the test logic.
- **Keep file size manageable.** No single code file may be longer than 400
  lines. Long switch statements or dispatch tables should be broken up by
  feature and constituents colocated with targets. Large blocks of test data
  should be moved to external data files.

## Documentation Maintenance

- **Reference:** Use the markdown files within the `docs/` directory as a
  knowledge base and source of truth for project requirements, dependency
  choices, and architectural decisions.
- **Update:** When new decisions are made, requirements change, libraries are
  added/removed, or architectural patterns evolve, **proactively update** the
  relevant file(s) in the `docs/` directory to reflect the latest state.
  **Ensure the documentation remains accurate and current.**
- Documentation must use en-GB-oxendict ("-ize" / "-yse" / "-our") spelling
  and grammar. (EXCEPTION: the naming of the "LICENSE" file, which is to be
  left unchanged for community consistency.)
- A documentation style guide is provided at
  `docs/documentation-style-guide.md`.

## Change Quality & Committing

- **Atomicity:** Aim for small, focused, atomic changes. Each change (and
  subsequent commit) should represent a single logical unit of work.
- **Quality Gates:** Before considering a change complete or proposing a commit,
  ensure it meets the following criteria:

  - New functionality or changes in behaviour are fully validated by relevant
    unittests and behavioural tests.
  - Where a bug is being fixed, a unittest has been provided demonstrating the
    behaviour being corrected both to validate the fix and to guard against
    regression.
  - Passes all relevant unit and behavioural tests according to the guidelines
    above. (Use `make test` to verify).
  - Passes lint checks. (Use `make lint` to verify).
  - Adheres to formatting standards tested using a formatting validator. (Use
    `make check-fmt` to verify).

- **Committing:**

  - Only changes that meet all the quality gates above should be committed.
  - Write clear, descriptive commit messages summarizing the change, following
    these formatting guidelines:

    - **Imperative Mood:** Use the imperative mood in the subject line (e.g.,
      "Fix bug", "Add feature" instead of "Fixed bug", "Added feature").
    - **Subject Line:** The first line should be a concise summary of the change
      (ideally 50 characters or fewer).
    - **Body:** Separate the subject from the body with a blank line. Subsequent
      lines should explain the *what* and *why* of the change in more detail,
      including rationale, goals, and scope. Wrap the body at 72 characters.
    - **Formatting:** Use Markdown for any formatted text (like bullet points or
      code snippets) within the commit message body.

- Do not commit changes that fail any of the quality gates.

## Refactoring Heuristics & Workflow

- **Recognizing Refactoring Needs:** Regularly assess the codebase for potential
  refactoring opportunities. Consider refactoring when you observe:
- **Long Methods/Functions:** Functions or methods that are excessively long
    or try to do too many things.
- **Duplicated Code:** Identical or very similar code blocks appearing in
    multiple places.
- **Complex Conditionals:** Deeply nested or overly complex `if`/`else` or
    `switch` statements (high cyclomatic complexity).
- **Large Code Blocks for Single Values:** Significant chunks of logic
    dedicated solely to calculating or deriving a single value.
- **Primitive Obsession / Data Clumps:** Groups of simple variables (strings,
    numbers, booleans) that are frequently passed around together, often
    indicating a missing class or object structure.
- **Excessive Parameters:** Functions or methods requiring a very long list of
    parameters.
- **Feature Envy:** Methods that seem more interested in the data of another
    class/object than their own.
- **Shotgun Surgery:** A single change requiring small modifications in many
    different classes or functions.
- **Post-Commit Review:** After committing a functional change or bug fix (that
  meets all quality gates), review the changed code and surrounding areas using
  the heuristics above.
- **Separate Atomic Refactors:** If refactoring is deemed necessary:
- Perform the refactoring as a **separate, atomic commit** *after* the
    functional change commit.
- Ensure the refactoring adheres to the testing guidelines (behavioural tests
    pass before and after, unit tests added for new units).
- Ensure the refactoring commit itself passes all quality gates.

## Rust Specific Guidance

This repository is written in Rust and uses Cargo for building and dependency
management. Contributors should follow these best practices when working on the
project:

- Run `make fmt`, `make lint`, and `make test` before committing. These targets
  wrap `cargo fmt`, `cargo clippy`, and `cargo test` with the appropriate flags.
- Clippy warnings MUST be disallowed.
- Fix any warnings emitted during tests in the code itself rather than
  silencing them.
- Where a function is too long, extract meaningfully named helper functions
  adhering to separation of concerns and CQRS.
- Where a function has too many parameters, group related parameters in
  meaningfully named structs.
- Where a function is returning a large error consider using `Arc` to reduce the
  amount of data returned.
- Every module **must** begin with a module level (`//!`) comment explaining the
  module's purpose and utility.
- Document public APIs using Rustdoc comments (`///`) so documentation can be
  generated with cargo doc.
- Prefer immutable data and avoid unnecessary `mut` bindings.
- Handle errors with the `Result` type instead of panicking where feasible.
- Use explicit version ranges in `Cargo.toml` and keep dependencies up-to-date.
- Avoid `unsafe` code unless absolutely necessary and document any usage
  clearly.
- Place function attributes **after** doc comments.
- Do not use `return` in single-line functions.
- Use predicate functions for conditional criteria with more than two branches.
- Lints must not be silenced except as a **last resort**.
- Lint rule suppressions must be tightly scoped and include a clear reason.
- Prefer `expect` over `allow`.
- Where a function is unused with specific features selected, use conditional
  compilation with `#[cfg]` or `#[cfg_attr]`.
- Prefer `.expect()` over `.unwrap()`.
- Use `concat!()` to combine long string literals rather than escaping newlines
  with a backslash.
- Prefer single line versions of functions where appropriate. I.e.,

  ```rust
  pub fn new(id: u64) -> Self { Self(id) }
  ```

  Instead of:

  ```rust
  pub fn new(id: u64) -> Self {
      Self(id)
  }
  ```

### Testing

- Write unit and behavioural tests for new functionality. Run both before and
  after making any change.
- Use `rstest` fixtures for shared setup.
- Replace duplicated tests with `#[rstest(...)]` parameterized cases.
- Prefer `mockall` for mocks/stubs.
- Mock non-deterministic dependencies (e.g., environment variables and the
  system clock) using dependency injection with the `mockable` crate (traits
  like `Env` and `Clock`) where appropriate. See
  `docs/reliable-testing-in-rust-via-dependency-injection.md` for guidance.

### Dependency Management (Rust)

- **Mandate caret requirements for all dependencies.** All crate versions
  specified in `Cargo.toml` must use SemVer-compatible caret requirements
  (e.g., `some-crate = "1.2.3"`). This is Cargo's default and allows for safe,
  non-breaking updates to minor and patch versions while preventing breaking
  changes from new major versions. This approach is critical for ensuring build
  stability and reproducibility.
- **Prohibit unstable version specifiers.** The use of wildcard (`*`) or
  open-ended inequality (`>=`) version requirements is strictly forbidden, as
  they introduce unacceptable risk and unpredictability. Tilde requirements
  (`~`) should only be used where a dependency must be locked to patch-level
  updates for a specific, documented reason.

### Error Handling (Rust)

- **Prefer semantic error enums**. Derive `std::error::Error` (via the
  `thiserror` crate) for any condition the caller might inspect, retry, or map
  to an HTTP status.
- **Use an *opaque* error only at the app boundary**. Use `eyre::Report` for
  human-readable logs; these should not be exposed in public APIs.
- **Never export the opaque type from a library**. Convert to domain enums at
  API boundaries, and to `eyre` only in the main `main()` entrypoint or
  top-level async task.

## Markdown Guidance

- Validate Markdown files using `make markdownlint`. This target also runs the
  pinned `typos` spelling gate for en-GB-oxendict prose.
- Run `make spelling` to check spelling directly. Generate `typos.toml` with
  `scripts/generate_typos_config.py`; never edit generated entries by hand.
  Add narrow repository exceptions to `typos.local.toml` instead.
- Run `make fmt` after any documentation changes to format all Markdown
  files and fix table markup.
- Validate Mermaid diagrams in Markdown files by running `make nixie`.
- Markdown paragraphs and bullet points must be wrapped at 80 columns.
- Code blocks must be wrapped at 120 columns.
- Tables and headings must not be wrapped.
- Use dashes (`-`) for list bullets.
- Use GitHub-flavoured Markdown footnotes (`[^1]`) for references and
  footnotes.

## TypeScript Frontend Guidance (Client‑Side Only)

**Stack**: Bun · Biome · Vite (esbuild under the hood for dev) · React ·
Tailwind CSS v4 · daisyUI v5 · TanStack (Query/Router/Table).

This document mirrors the intent of the Rust guidance—strictness, clarity, and
predictable builds—translated into idiomatic, modern TypeScript and a
browser‑only runtime.

### Toolchain & Project Shape

- **ESM‑only**: Source and build outputs are ES Modules. No CommonJS. Configure
  Vite accordingly; package publishes only ESM (for libraries) or static assets
  (for apps).
- **Runtime targets**: Target modern evergreen browsers. Use `browserslist` to
  define the support matrix; drop legacy where feasible. Prefer native Web APIs
  (Fetch, URL, AbortController, Streams).
- **Bun as runner**: Use Bun for scripts and dev server invocations. Prefer
  `bun run` for scripts and `bunx` for one‑off CLIs.
- **Workspaces (optional)**: If a monorepo, use `pnpm` or Bun workspaces with
  clear package boundaries and TS project references.
- **Vite**: Default bundler for dev/build. Enable code‑splitting, prefetch
  hints, and asset hashing. Esbuild handles TS/JS transforms in dev; production
  uses Rollup via Vite.
- **Project scripts (Bun)**:
- `fmt`: `biome format --write .`
- `lint`: `biome ci . && tsc -p tsconfig.json --noEmit`
- `typecheck`: `tsc -p tsconfig.json --noEmit`
- `dev`: `vite`
- `build`: `vite build`
- `preview`: `vite preview`
- `test`: `vitest run --coverage`
- `audit`: `bun x pnpm@latest audit`
- `audit:snyk`: `bun x snyk test`
- Note: `audit` requires a committed `bun.lock`; `audit:snyk` requires
      installed dependencies—run `bun install` before invoking it.

  In this repository, Biome is orchestrated via the Makefile along with Rust
  tooling. Prefer these entry points locally and in CI:

  ```bash
  # Format all code (Rust + JS/TS via Biome)
  make fmt

  # Lint all code (Clippy + Biome CI)
  make lint

  # Check formatting only (no writes)
  make check-fmt
  ```

  You can also call Biome directly through Bun when needed:

  ```bash
  bun x biome format --write
  bun x biome ci frontend-pwa packages/tokens/src packages/tokens/build packages/types/src
  ```

### Compiler Configuration (Make It Sharp)

Use a strict `tsconfig.json` suitable for browser builds:

- `strict: true`
- `noUncheckedIndexedAccess: true`
- `exactOptionalPropertyTypes: true`
- `noImplicitOverride: true`
- `useUnknownInCatchVariables: true`
- `noPropertyAccessFromIndexSignature: true`
- `verbatimModuleSyntax: true` (and use `import type` / `export type`)
- `moduleResolution: "bundler"` (lets Vite resolve modern packages)
- `lib`: include only what you need (e.g., `dom`, `dom.iterable`, `es2022`)
- Do not emit from `tsc` in app packages (`noEmit: true`); Vite handles
  emission.

**Order**: Place JSDoc comments above declarations and above any decorators.
Keep docs close to code.

### Code Style & Structure

- **Immutability first**: Prefer `const`, `readonly`, and `Readonly<T>`; avoid
  mutating props or inputs.
- **Functions**: Extract meaningfully named helpers when a function grows long.
  Keep trivial functions on one line when readability allows:

  ```ts
  export const mkId = (n: number): Id => new Id(n);
  ```

- **Parameters**: Group related parameters into typed objects or builders;
  avoid long positional lists.
- **Predicates**: When `if/else` grows beyond two branches, extract a predicate
  function or use a lookup table. Ensure exhaustive `switch` with a `never`
  guard helper.
- **Docs**: Every module begins with a `/** @file … */` block describing
  purpose, responsibilities, and usage.
- **Public APIs (for libs)**: Export explicit entry points via `package.json`
  `exports`/`types`. Avoid wildcard re‑exports that mask breaking changes.

### Runtime Validation & Types

- **Runtime schemas**: Validate I/O boundaries (network responses, localStorage
  payloads, URL params) with `zod`/`valibot`. Generate TS types from schemas or
  derive schemas from types, but add a CI check to keep them in sync.
- **Nominal branding**: Use branded types for IDs/tokens to avoid accidental
    mixing:

    ```ts
    type UserId = string & { readonly brand: "UserId" };
    ```

- **Cancellation**: Accept `AbortSignal` for any async that can hang (fetches,
  long UI work). Wire signals through TanStack Query via `signal` in fetchers.
- **Time & RNG**: Centralize `now()` and `rng()` adapters; never call
  `Date.now()` or `Math.random()` directly in business logic.

### Error Handling (Frontend)

- **Semantic errors**: Use discriminated unions for recoverable conditions
  callers might branch on (e.g.,
  `{ type: "rate_limited"; retryAfterMs: number }`).
- **Exceptions**: Reserve `Error` subclasses for exceptional paths
  (framework/edge). Always attach a `cause` where available.
- **App boundary**: Map domain errors to user‑facing messages in UI components
  only. Never leak raw stack traces to the DOM or logs shipped to analytics.

### Testing (Unit, Behavioural, and UI)

- **Runner**: Vitest with `jsdom` (or `happy-dom`) for component tests. Keep
  tests parallel‑safe and deterministic.
- **Fixtures**: Use factories/builders for component props and server
  responses. Avoid ad hoc object literals in tests.
- **Parameterized tests**: Prefer table‑driven cases via `test.each` /
  `it.each`.
- **Mocking**: Use `vi.mock` for module boundaries. Inject adapters for
  env/time/storage/fetch; do not monkey‑patch globals in product code.
- **Fake timers**: `vi.useFakeTimers()` for time‑based logic; restore after
  each test.
- **Snapshots**: Keep deterministic by sorting keys and fixing seeds. Limit
  snapshot scope to stable UI fragments.
- **E2E (optional)**: Playwright for flows critical to revenue or safety; keep
  the set minimal and fast.

### Dependency Management (Frontend)

- **Version policy**: Use caret requirements (`^x.y.z`) for all direct
  dependencies. Avoid `*`, `>=` or tag aliases like `latest`. Use tilde
  (`~x.y.z`) only with a documented justification.
- **Lockfile**: Commit `bun.lock`. Recreate on major tool upgrades; keep
  `bun.lockb` ignored.
- **Audit**: Run `bun run audit` locally and in automation. Track exceptions
  with explicit expiry dates.
- **Culling**: Prefer small, actively maintained packages. Remove unmaintained
  or risky dependencies swiftly.

### Linting & Formatting

- **Biome**: One tool for format + lint. Configure with strict rules: disallow
  `any`, no non‑null `!`, forbid `@ts-ignore` in favour of `@ts-expect-error`
  (with a reason).
  - In this repo: use `make fmt`, `make lint`, and `make check-fmt`.
  - Biome respects `.biomeignore` and VCS ignore files; large build trees like
    any `target/` directory are excluded.
- **Type‑checking**: `tsc --noEmit` as part of `lint` to catch type errors
  early.
- **Import hygiene**: Enforce sorted, grouped imports; no unused or extraneous
  dependencies.

### Performance & Correctness

- **Code‑splitting**: Use Vite’s dynamic `import()` to split routes and heavy
  feature bundles.
- **TanStack Query**: Use stale‑time, cache‑time, and prefetch strategically.
  Avoid `refetchOnWindowFocus` unless the data truly needs it.
- **Async**: Avoid `await` inside loops; batch with `Promise.allSettled`. Use
  `async` iterables/streams for large data.
- **Rendering**: Enable React StrictMode in dev; memoize expensive components;
  prefer derived data via selectors.
- **Stability**: Keep JSON stable (deterministic key order) for snapshots and
  client‑side caches.

### Security & Privacy (Client‑Side)

- **CSP**: Ship a Content Security Policy where deployment allows it. For SPA
  hosting, prefer hashed scripts and forbid `eval`/`new Function`.
- **Trusted Types**: If embedding third‑party HTML, gate through a sanitizer
  and (where supported) Trusted Types policies.
- **Secrets**: Never hard‑code secrets in client bundles. Use public,
  least‑privilege tokens only; treat everything as public.
- **Origin hygiene**: Centralize fetch base URLs; validate response schemas;
  handle opaque redirects.
- **Storage**: Encrypt sensitive data server‑side; treat client storage as
  untrusted. Namespaced keys; versioned payloads; schema‑validated reads.

### React, Tailwind 4, and daisyUI 5

- **Tailwind v4**: Use the new config conventions and JIT‑only pipeline.
  Co‑locate `@apply` in component‑scoped CSS when it improves clarity; prefer
  utilities otherwise. Remove unused utilities via content‑aware purge in
  production.
- **daisyUI v5**: Keep theme tokens in sync with Tailwind config. Extend rather
  than override where possible; avoid deep custom CSS that fights component
  variables.
- **Design tokens**: Define a single source of truth (CSS variables) for
  colour, spacing, radius, and typography. Expose tokens to Tailwind via
  `theme.extend` to keep utilities aligned with design.
- **A11y**: Use semantic HTML first. Prefer daisyUI components only where they
  don’t harm semantics. Audit focus states and colour contrast with automated
  checks.
- **Radix UI**: Build behaviour with Radix primitives and layer DaisyUI/Tailwind
  classes for presentation.
- **Purity**: Export view components as pure functions with props treated as
  read‑only. Move state, effects, and translations into dedicated `use*` hooks.
- **Component tests**: Use React Testing Library under Vitest for rendering and
  user‑centric assertions.

### TanStack Usage Notes

- **Query**: Co‑locate query keys and fetchers; prefer stable keys; use
  `select` to project server data for components. Wire `AbortSignal` to
  fetches. Use `retry` policies appropriate to the endpoint.
- **Router** (if used): Code‑split per route; prefetch data on navigation where
  it improves perceived performance. Handle not‑found/unauthorised with typed
  loaders.
- **Table** (if used): Keep row models pure; virtualize for large sets; memoize
  column defs.
- **State**: Encapsulate server state with TanStack Query and model complex
  local state with reducers or state machines inside custom hooks.

### Internationalization

- **Setup**: Initialize `react-i18next` with `i18next-http-backend` and
  `i18next-browser-languagedetector`; set `fallbackLng: 'en'`.
- **Translations**: Store locale files under `public/locales/<lang>/<ns>.json`
  and load strings by namespace.
- **Hooks**: Call `useTranslation` within logic hooks and pass all translated
  strings to view components via props.

### Testing (Vitest & Playwright)

- **Vitest config**: Use the `jsdom` environment, include `tests/setup.ts`, and
  prioritize running `**/*.a11y.test.ts` in a dedicated Vitest invocation
  before the rest of the suite.
- **axe integration**: Import `vitest-axe/extend-expect` in `tests/setup.ts` and
  list this file in `tsconfig.json` so the matcher types load.
- **Rule gaps**: Disable `color-contrast` and `scrollable-region-focusable`
  rules in Vitest (jsdom limits these checks); verify them in Playwright.
- **Playwright**: Run `@axe-core/playwright` scans, exercise keyboard
  navigation, capture accessibility tree snapshots, and emulate locales to test
  translations.

### Observability (Frontend)

- **Structured logs**: Gate debug logs behind a flag (`?debug=1` or build‑time
  define). Use a small logger that emits structured objects in dev and terse
  strings in prod.
- **Metrics**: Basic RUM—navigation timings, error counts, and SPA route
  transitions. Sample aggressively to preserve privacy and cost.
- **Feature flags**: Centralize flags; keep a kill‑switch for risky features;
  document fallback behaviour.

### Documentation & Examples

- **Literate examples**: Keep small TS snippets in docs that compile during
  builds (typecheck only). Prefer examples that mirror production patterns
  (schema‑validated fetchers, `AbortSignal`, TanStack Query hooks).
- **Module headers**: Each file begins with `/** @file … */` stating purpose,
  invariants, and cross‑links to related modules.
- **Error semantics**: Document user‑visible failure modes next to components
  and hooks that surface them.

### Release Discipline

- **Conventional Commits + Changesets** for versioning (libraries) and change
  logs.
- **SemVer**: Honour breaking changes with a major bump; avoid sneaking them in
  via dependency updates.
- **Reproducibility**: Pin tool versions via `.tool-versions`/`.bun-version`
  (or document required Bun/Node versions). Rebuild the lockfile on major
  upgrades.
- **Bundle sanity**: Maintain a bundle size budget; track regressions; document
  acceptable variances when adding large features.

### Quick Checklist (Before Commit)

- `bun run fmt`, `bun run lint`, `bun run test` all clean; no Biome warnings;
  no TypeScript errors; coverage thresholds hold.
- `bun run audit` passes or has justified, time‑boxed exceptions.
- No `any`, no `@ts-ignore`; use `@ts-expect-error` only with a reason.
- All async APIs accept `AbortSignal` where relevant; all fetchers validated
  against runtime schemas.
- Module headers present; public exports documented; design tokens consistent
  across Tailwind/daisyUI.

## Additional tooling

The following tooling is available in this environment:

- `mbake` – A Makefile validator. Run using `mbake validate Makefile`.
- `strace` – Traces system calls and signals made by a process; useful for
  debugging runtime behaviour and syscalls.
- `gdb` – The GNU Debugger, for inspecting and controlling programs as they
  execute (or post-mortem via core dumps).
- `ripgrep` – Fast, recursive text search tool (`grep` alternative) that
  respects `.gitignore` files.
- `ltrace` – Traces calls to dynamic library functions made by a process.
- `valgrind` – Suite for detecting memory leaks, profiling, and debugging
  low-level memory errors.
- `bpftrace` – High-level tracing tool for eBPF, using a custom scripting
  language for kernel and application tracing.
- `lsof` – Lists open files and the processes using them.
- `htop` – Interactive process viewer (visual upgrade to `top`).
- `iotop` – Displays and monitors I/O usage by processes.
- `ncdu` – NCurses-based disk usage viewer for finding large files/folders.
- `tree` – Displays directory structure as a tree.
- `bat` – `cat` clone with syntax highlighting, Git integration, and paging.
- `delta` – Syntax-highlighted pager for Git and diff output.
- `tcpdump` – Captures and analyses network traffic at the packet level.
- `nmap` – Network scanner for host discovery, port scanning, and service
  identification.
- `lldb` – LLVM debugger, alternative to `gdb`.
- `eza` – Modern `ls` replacement with more features and better defaults.
- `fzf` – Interactive fuzzy finder for selecting files, commands, etc.
- `hyperfine` – Command-line benchmarking tool with statistical output.
- `shellcheck` – Linter for shell scripts, identifying errors and bad practices.
- `fd` – Fast, user-friendly `find` alternative with sensible defaults.
- `checkmake` – Linter for `Makefile`s, ensuring they follow best practices and
  conventions.
- `srgn` – [Structural grep](https://github.com/alexpovel/srgn), searches code
  and enables editing by syntax tree patterns.
- `difft` **(Difftastic)** – Semantic diff tool that compares code structure
  rather than just text differences.

## Python Development Guidelines

For Python development, refer to the detailed guidelines in the `.rules/`
directory:

- [Python Code Style Guidelines](.rules/python-00.md) - Core Python 3.13 style
  conventions
- [Python Context Managers](.rules/python-context-managers.md) - Best practices
  for context managers
- [Python Exceptions and
  Logging(.rules/python-exception-design-raising-handling-and-logging.md) -
  Throwing, catching and logging exceptions.
- [Python Generators](.rules/python-generators.md) - Generator and iterator
  patterns
- [Python Project Configuration](.rules/python-pyproject.md) - pyproject.toml
  and packaging
- [Python Return Patterns](.rules/python-return.md) - Function return
  conventions
- [Python Typing](.rules/python-typing.md) - Type annotation best practices

Additional docs:

- [Scripting Standards](docs/scripting-standards.md) - Guidance for writing
  robust scripts

## Key Takeaway

These practices help maintain a high-quality codebase and facilitate
collaboration.
