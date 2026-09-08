# Hermes Agent - Development Guide

Instructions for AI coding assistants and developers working on the hermes-agent codebase.
This root file holds only what applies everywhere. Each area has its own `AGENTS.md` (aim for
~8k chars; `agent/subdirectory_hints.py` delivers up to 32k and truncates head/tail with a warning
past that); see the **routing table** at the end and read the area file before editing in that area.

**Never give up on the right solution.**

## Sandbox false negatives

- `pre_llm_call.is_worker` reports delegation/background review, independent
  of parent-session lineage. A compaction successor must retain the main
  owner's context rehydration. Plugins keep principal/profile/offline gates.

- **Do not mistake sandbox loopback denial for gbrain downtime.** If a gbrain
  MCP or CLI read fails with `ECONNREFUSED 127.0.0.1:5432` (or an equivalent
  local PostgreSQL connection error) inside the filesystem/network sandbox,
  immediately retry the same read-only call with approved out-of-sandbox
  access. Declare gbrain unavailable only if that retry also fails. Do not
  start, restart, or otherwise mutate the database service merely to diagnose
  the sandbox false negative.

## What Hermes Is

Hermes is a personal AI agent that runs the same agent core across a CLI, a messaging
gateway (Telegram, Discord, Slack, ~20 platforms), a TUI, and an Electron desktop app. It
learns across sessions (memory + skills), delegates to subagents, runs scheduled jobs, and
drives a real terminal and browser. It is extended primarily through **plugins and skills**,
not by growing the core.

Two invariants shape almost every design decision and are the lens for reviewing any change:

- **Per-conversation prompt caching is sacred.** A long-lived conversation reuses a cached
  prefix every turn. Anything that mutates past context, swaps toolsets, reloads memories, or
  rebuilds the system prompt mid-conversation invalidates that cache and multiplies the user's
  cost. We do not do it; the ONE exception is context compression. Slash commands that mutate
  system-prompt state (skills, tools, memory) must be **cache-aware**: default to deferred
  invalidation (takes effect next session) with an opt-in `--now` flag (`/skills install --now`
  is the canonical pattern).
- **The core is a narrow waist; capability lives at the edges.** Every model tool is sent on
  every API call, so the bar for a new *core* tool is high. New capability should arrive as a
  CLI command + skill, a service-gated tool, or a plugin — not as core surface.

## Contribution Rubric — What We Want / What We Don't

The project's intent layer. It serves humans aiming a contribution AND the automated triage
sweeper, which may only close on `implemented_on_main`, `cannot_reproduce`, or `incoherent`.
Taste-based "out of scope" closes are a human maintainer's call; the sweeper's job is to
recognize design intent and *avoid wrongly closing a legitimate contribution*.

Read the balance right: Hermes ships a **lot**. Most merges are bug fixes to reported
behavior, and the product surface (platforms, providers, models, desktop/TUI features)
expands aggressively on purpose. The restraint below targets the **core agent + model tool
schema**, the one place where every addition is paid for on every API call. "Smallest
footprint" governs *how a capability is wired into the core*, not whether the product may
grow: expansive at the edges, conservative at the waist.

### What we want

- **Fix real bugs, well.** Reproduce the symptom on current `main`, point to the exact line
  where it manifests, and fix the whole bug class — sibling call paths included.
- **Expand reach at the edges.** New adapters, channels, providers, models, desktop/TUI/
  dashboard features land routinely, including large ones — as long as they integrate with
  the existing setup/config UX (`hermes tools`, `hermes setup`, auto-install) rather than
  bolting on a raw env var.
- **Refactor god-files into clean modules.** Huge mechanical `+N/-N` extraction PRs are
  wanted work. "Every line traces to the request" applies to *feature* PRs; a declared
  refactor's request IS the extraction.
- **Keep the core narrow.** Prefer, in order: extend existing code → CLI command + skill →
  service-gated tool (`check_fn`) → plugin → MCP server in the catalog → new core tool (last
  resort). See the Footprint Ladder.
- **Extend, don't duplicate.** Check whether existing infrastructure covers the use case
  before adding a module/manager/hook. When 3+ open PRs integrate the same *category*
  (memory backends, providers, notifiers), design an ABC + orchestrator, wrap the existing
  built-in as the first provider, and turn the competing PRs into plugins against it.
- **Behavior contracts over snapshots.** Tests assert how two pieces of data relate, never
  freeze a current value (see Testing).
- **E2E validation, not just green unit mocks.** Anything touching resolution chains, config
  propagation, security boundaries, remote backends, or file/network I/O must exercise the
  real path with real imports against a temp `HERMES_HOME`. Mocks hide integration bugs.
- **Cache-, alternation-, and invariant-safe.** Preserve prompt caching, strict role
  alternation (never two same-role messages in a row; never a synthetic user message injected
  mid-loop), and a system prompt byte-stable for the life of a conversation.
- **Contributor credit preserved.** Salvage external work by cherry-picking (rebase-merge) so
  authorship survives; build on top rather than reimplementing.

### What we don't want (rejected even when well-built)

- **Speculative infrastructure.** Hooks/callbacks/extension points with no concrete consumer.
  Adding a hook is easy; removing one after plugins depend on it is hard. A hook with a real,
  stated use case is NOT speculative even if the consumer ships separately.
- **New `HERMES_*` env vars for non-secret config.** `.env` is for secrets only. Behavioral
  settings (timeouts, thresholds, flags, display prefs) go in `config.yaml`; bridge to an
  internal env var in code if the mechanism needs one. Reject "set X in your .env" docs
  unless X is a credential.
- **A new core tool when terminal + file (or a skill) already do the job.** If the only
  barrier is file visibility on a remote backend, fix the mount, not the toolset.
- **Lazy-reading escape hatches on instructional tools.** No `offset`/`limit` pagination on
  tools that load content the agent must read fully (skills, prompts, playbooks) — models
  read page 1 and skip the rest.
- **"Fixes" that destroy the feature they secure.** Read the original intent
  (`git log -p -S`) before restricting behavior; find a fix that preserves the feature.
- **Outbound telemetry / usage attribution without opt-in gating.** No analytics,
  third-party identifier tagging, or attribution tags until a generic user-facing opt-in
  (config gate + setup prompt + `hermes tools` toggle) exists. Park behind a label.
- **Change-detector tests, cache-breaking mid-conversation, dead code wired in without E2E
  proof, plugins that touch core files.** Plugins work within the ABCs/hooks we provide; if
  one needs more, widen the generic plugin surface, never special-case it in core.
- **Third-party products integrated into the core tree.** Observability backends, vendor
  SaaS connectors, analytics dashboards, and other "someone else's product" plugins do NOT
  land under `plugins/` — every one becomes our burden against a fast-moving core for a
  backend we don't own. Ship as a **standalone plugin repo** (`~/.hermes/plugins/` or pip
  entry point), promoted in the Nous Research Discord `#plugins-skills-and-skins`. This is a
  coupling decision, not a quality bar; such PRs are closed with a pointer to publish.

### Before you call it a bug — verify the premise (and when NOT to close)

The most common reason a well-written PR is closed is a **wrong premise** or treating an
**intentional design as a gap**. These patterns tell a reviewer what to scrutinize and tell
the sweeper when a PR is NOT safe to close (when in doubt, leave it open for a human):

- **"Intentional design, not a gap."** Ask whether the isolation IS the design. Profiles are
  independent islands on purpose: a PR adding live config inheritance from the default
  profile was closed because coupling profiles is exactly what the design prevents (`--clone`
  already covers "start from my default"). Read `git log -p -S "<symbol>"` before assuming
  something is unfinished.
- **"The premise doesn't hold against how X actually works."** Trace the real runtime before
  accepting a rationale. Real closes: a rate-limit "re-probe during cooldown" PR (the breaker
  trips only on a *confirmed-empty* bucket, so re-probing hammers a bucket proven empty); a
  usage fix whose new branch **never executes** because an earlier guard already popped the
  state. If you can't point to the exact line where the bug manifests AND show the fix changes
  that line's behavior, the premise is unverified.
- **"The absence was deliberate."** Restoring "missing" `__init__.py` files made a test tree
  importable as a dotted package that shadowed the real plugin and deleted its `register()`
  at import time. The omission was load-bearing.
- **"Overreached / resurrected an approach we moved past."** Scope creep beyond the agreed
  base, or reviving a direction maintainers closed, is rejected even when it works. Offer the
  rest as a focused follow-up.

Throughline: **verify the claim AND the intent against the codebase before writing or merging
a fix.** A reproduction on current `main` plus a line-level account beats a plausible
rationale. When unsure about intent, asking is cheaper than shipping a fix that fights the
design.

### The Footprint Ladder (new capability decision)

Choose the highest (least-footprint) rung that correctly solves the problem:

1. **Extend existing code** — a variation of something that exists. Zero new surface.
2. **CLI command + skill** — config/state/infra expressible as shell commands; the agent runs
   `hermes <subcommand>` guided by a skill. Default for subscriptions, scheduled tasks,
   service setup (`hermes webhook`, `hermes cron`, `hermes tools`).
3. **Service-gated tool (`check_fn`)** — needs structured params/returns AND only appears when
   a prerequisite is configured (Home Assistant tools, memory-provider tools).
4. **Plugin** — third-party/niche/user-specific; lives in `~/.hermes/plugins/` or a pip
   package, discovered at runtime.
5. **MCP server (in the catalog)** — genuinely a tool but not core-fundamental. Zero permanent
   core-schema footprint, reusable by any MCP host, reached via the built-in MCP client.
6. **New core tool** — only when fundamental, broadly useful to nearly every user, and
   unreachable via terminal + file or an MCP server (terminal, read_file, web_search,
   browser_navigate).

### Surface capability is a property of the SESSION, never of the process env

A tool that works only because of *who is on the other end* (desktop panes, in-app browser,
message reactions, Projects) must resolve availability from the **session's own source**, not
from an env var on the backend. Client and backend are separate machines: the desktop app may
drive a locally spawned backend, one over SSH, one behind URL + token, or Hermes Cloud, and
only the first two carry `HERMES_DESKTOP=1`. An env-keyed gate is a silent no-op on the other
topologies — the tool is stripped from the schema while the platform hint tells the model it
is "inside the Hermes desktop app". The pattern:

- **The toolset is the surface gate.** Keep such tools off `_HERMES_CORE_TOOLS` and in a named
  toolset (`desktop_ui`, `project`); the GUI gateway's `_load_enabled_toolsets(platform)`
  folds it in when the session's platform says GUI. One resolver, every topology.
- **`check_fn` answers reachability or opt-in, not surface.** "Is the bridge wired?" — fine.
  "Was I spawned by Electron?" — not. `check_fn` results are TTL-cached process-wide
  (`tools/registry.py`); a per-session answer does not belong there.
- **Ask which identity you mean.** `HERMES_DESKTOP=1` legitimately means "this backend was
  spawned by the app" (cron ticker, web-dist handling). It does NOT mean "a GUI is watching";
  the embedded terminal pane (`hermes --tui` against that backend) is the counterexample.

Test: if the capability still makes sense with the client on another machine, it is
session-scoped. Assert the GUI session gets the tool **with the env var absent**.

## Development Environment

```bash
source .venv/bin/activate   # or: source venv/bin/activate
```
`scripts/run_tests.sh` probes `.venv`, then `venv`, then `$HOME/.hermes/hermes-agent/venv`
(worktrees sharing the main checkout's venv).

## Project Structure

Counts shift constantly; the filesystem is canonical. Load-bearing entry points:

```
hermes-agent/
├── run_agent.py          # AIAgent facade; the turn loop lives in agent/turn_*.py
├── model_tools.py        # Tool orchestration, discover_builtin_tools(), handle_function_call()
├── toolsets.py           # TOOLSETS dict, _HERMES_CORE_TOOLS
├── cli.py                # HermesCLI (REPL, slash dispatch) + hermes_cli/cli_*_mixin.py
├── hermes_state.py       # SessionDB facade; hermes_state_*.py siblings
├── hermes_constants.py   # get_hermes_home(), display_hermes_home() — profile-aware paths
├── hermes_logging.py     # agent.log / errors.log / gateway.log (profile-aware)
├── batch_runner.py       # Parallel batch processing
├── agent/                # turn_*.py loop phases, providers, memory, compression, prompt builder
├── hermes_cli/           # CLI subcommands, setup, config, plugins loader, skins, updater
│   └── web_routers/      # Dashboard FastAPI routers (one per surface); web_server.py mounts them
├── tools/                # Tool implementations, auto-discovered via tools/registry.py
│   └── environments/     # Terminal backends (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # run.py facade + run_*.py phases + session*.py + platforms/
│   ├── platforms/        # One adapter per platform; see platforms/ADDING_A_PLATFORM.md
│   └── builtin_hooks/    # Always-registered gateway hooks (extension point; none shipped)
├── plugins/              # memory/, context_engine/, model-providers/, kanban/, image_gen/, ...
├── skills/               # Built-in skills (by category)   optional-skills/: shipped, not active
├── ui-tui/               # Ink (React) terminal UI — `hermes --tui`
├── tui_gateway/          # Python JSON-RPC backend for TUI + Desktop — server.py + methods_*.py
├── apps/desktop/         # Electron desktop app (+ apps/shared JSON-RPC client)   web/: dashboard SPA
├── acp_adapter/          # ACP server (VS Code / Zed / JetBrains)
├── cron/                 # jobs.py + scheduler.py (+ scheduler_*.py)
├── evals/                # Offline benchmarks (codebase_navigability/, compaction/, ...)
├── scripts/              # run_tests.sh, release.py, check_compat_pointers.py, ci/
├── website/              # Docusaurus docs (developer-guide/ holds the long-form area docs)
└── tests/                # Pytest suite (~39k tests / ~3.7k files, Sep 2026)
```

**User state:** `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (secrets only),
`~/.hermes/logs/` (`agent.log` INFO+, `errors.log` WARNING+, `gateway.log`); all
profile-aware via `get_hermes_home()`. Browse logs with `hermes logs [--follow] [--level] [--session]`.

**Dependency chain:** `tools/registry.py` (no deps) ← `tools/*.py` (register at import) ←
`model_tools.py` (discovery) ← `run_agent.py`, `cli.py`, `batch_runner.py`, `environments/`.

### Facade + siblings layout (Sep 2026 decomposition)

Every former god file is a **facade** (public entry points + the names other packages import)
plus **siblings** `<stem>_<topic>.py` in the same directory, each owning one topic. Largest
families: `hermes_state.py` (21), `gateway/run.py` (15), `tools/mcp_tool.py` (15),
`hermes_cli/kanban.py` (14), `hermes_cli/web_server.py` (13 + 24 routers), `hermes_cli/auth.py`
(12), `tools/browser_tool.py` (11), `cli.py` (12 `hermes_cli/cli_*_mixin.py`), `run_agent.py`
(`agent/turn_*.py`, `agent_init.py`, `conversation_loop.py`).

- **Find code by topic, not by facade:** `grep -rn "def name" <dir>/<stem>_*.py`. Reading the
  facade first is the expensive way (`evals/codebase_navigability/`).
- **Siblings may import each other and late-import the facade** inside functions. A facade
  never imports a sibling at module level *and* gets imported by that sibling at module level.
- **Patch where production reads.** Siblings often do `from <facade> import name` inside the
  function so `monkeypatch.setattr(facade, "name", ...)` is the seam; a patch on the defining
  module passes silently. Check the call site's binding before writing a patch target
  (blind repointing to defining modules broke 130+ tests).
- **Compat pointers are OFF LIMITS in-tree.** Old import paths kept alive for external plugins
  (`PLUGIN-COMPAT` blocks, `COMPAT_MANIFEST.md`, `compat_manifest.json`) must not be used by
  in-tree code or tests; `scripts/check_compat_pointers.py` runs in CI, and
  `-W error::hermes_cli.plugin_compat.HermesPluginCompatWarning` catches them in the suite.
  They are removed 2026-09-14 by reverting one commit. Import from the defining module.
- **Don't recreate god files.** A file passing ~2,000 lines or a function passing ~300 lines /
  cyclomatic complexity 30 is the signal to split along `<stem>_<topic>` FIRST, in its own
  commit. New behaviour goes in a new or topical sibling — never appended to a facade.
- **No `if/elif` ladders ≥ 4 branches keyed on a name/kind** — use a dict/table → handler
  (`_SLASH_DISPATCH` in `cli.py`, `_command_handler_table` in the gateway are the shape).
- **No re-export shims for internal moves** ("keep the old name importable"). Internal paths
  are not API; external compat is handled ONCE by the compat layer, not per PR.
- **Moving a symbol means fixing its docs in the same PR:** grep `website/docs`, `docs/`,
  `skills/`, and every `AGENTS.md` for the old `path.py` + symbol (23 doc files went stale
  after the refactor). `evals/codebase_navigability/static_metrics.py <tree> <label>` measures
  file/function/CC/elif distributions before/after a large PR in ~2 min.

## Code Shape Rules (all languages)

- No "defense-in-depth" wrappers, `try/except: pass` around code that cannot fail, or flags
  nobody sets. Docstrings/comments keep the WHY, cut the WHAT.
- **Never infer process identity from argv substrings** (`"serve" in cmdline`) — the bug class
  behind ~10 fleet-update issues (#90778, #87594, #78089, #76129, #91964). Use the canonical
  matchers `gateway.status.looks_like_gateway_command_line` and
  `hermes_cli.update_cmd._hermes_holder_subcommand`; flag sets are DERIVED from the parser
  (`_holder_value_flags()`), never hand-written; match FULL cmdlines and truncate only for
  display. Details: `hermes_cli/AGENTS.md`.
- **Never hardcode `~/.hermes`.** `get_hermes_home()` for code paths, `display_hermes_home()`
  for user-facing text (both from `hermes_constants`). Hardcoding breaks profiles (5 bugs in
  PR #3575). Module-level constants are fine — they cache after `_apply_profile_override()`
  sets `HERMES_HOME`. Profile operations themselves are HOME-anchored
  (`_get_profiles_root()` = `Path.home()/.hermes/profiles`) so `hermes -p x profile list`
  sees all profiles — intentional, not a bug.
- **Argparse alias dispatch:** `add_parser("list", aliases=["ls"])` sets `dest` to the literal
  the user typed (`"ls"`). Dispatch must accept both (caught PTY-testing `hermes webhook ls`).
- **Don't wire in dead code without E2E validation.** Unshipped code was dead for a reason;
  E2E the real resolution chain with real imports against a temp `HERMES_HOME` first.

### TypeScript style (desktop, TUI, website, future TS packages)

Small nanostores over component state when state is shared or read by distant UI; each
feature owns its atoms (chat near chat, shared in `src/store`); rendering components use
`useStore`, non-rendering actions read `$atom.get()`; never thread state through three
components when the leaf can subscribe; persistence sits beside the atom that owns it. Route
roots stay thin (compose routes + shell, never controllers). No monolithic hooks — one narrow
job each; colocated action modules over god hooks. Pure side-effect callbacks use the terse
void form `onState={st => void setGatewayState(st)}`; async handlers make intent explicit
`onClick={() => void save()}`. Interfaces for public props and shared object shapes (not
`type X = {...}`); extend React primitives (`React.ComponentProps<'button'>`, `Omit`, `Pick`).
Table-driven beats condition ladders for ids/routes/views. `src/app` owns routes/pages,
`src/store` shared atoms, `src/lib` pure helpers.

## Dependency Pinning Policy

All dependencies carry upper bounds (litellm compromise #2796/#2810; Mini Shai-Hulud worm,
May 2026). PyPI: `>=floor,<next_major` (`"httpx>=0.28.1,<1"`); pre-1.0: `<0.(minor+2)`
(`>=0.29,<0.32`). Git URLs: 40-char commit SHA. GitHub Actions: SHA + `# vN` comment. CI-only
pip: `==exact`. A bare `>=X.Y.Z` is rejected by CI and reviewers. Run `uv lock` after
changing `pyproject.toml`. Reference: #2810 (bounds), #9801 (SHA pinning + audit CI).

## Commits, Merges, PRs

- **Squash merges from stale branches silently revert recent fixes.** Before squash-merging,
  bring the branch to `main` (`git fetch origin main && git reset --hard origin/main`, re-apply
  the PR's commits). Verify with `git diff HEAD~1..HEAD` after merging — unexpected deletions
  are a red flag.
- Salvage by cherry-pick so contributor authorship survives (see rubric).
- Tests per fix: 1–2 INVARIANT tests (behaviour contract, proven red on base), never
  change-detectors; ≤ 2 tests is the salvage bar too. Reject/rewrite in salvaged diffs:
  appendages to facades, new god helpers, compat aliases, wrappers.

## Testing (applies everywhere)

**ALWAYS use `scripts/run_tests.sh`**, never bare `pytest`. It enforces CI parity: credential
vars unset, `TZ=UTC`, `LANG=C.UTF-8`, `HERMES_HOME` → temp dir, and per-file subprocess
isolation via `scripts/run_tests_parallel.py` (no xdist; workers scale with CPU count) so
module-level dicts/ContextVars cannot leak between files. Direct `pytest` on a big machine
with API keys set has caused repeated "works locally, fails in CI" incidents (and the reverse).

```bash
scripts/run_tests.sh                                    # full suite
scripts/run_tests.sh tests/gateway/                     # one directory
scripts/run_tests.sh tests/agent/test_foo.py -k test_x  # runner is file-granular; -k narrows
scripts/run_tests.sh -v --tb=long                       # pytest flags pass through
```

- **Flake policy:** a failing FILE is retried once in a fresh subprocess (`--file-retries`;
  `HERMES_TEST_FILE_RETRIES=0` disables). Pass-on-retry is green but printed under `⚠ FLAKY`
  with both outputs — a bug to fix, not noise. Timing tests must not assume a quiet runner:
  wall-clock bounds ≥ 2s, event-based sync, no `assert not _wait_until(...)` races.
- **Placement:** `scripts/ci/classify_changes.py` picks jobs by changed files. A Python test
  asserting about `package.json`, `package-lock.json`, `tsconfig.json`, or `.ts/.tsx/.js/
  .mjs/.cjs` sources will not run on a JS-only PR (green on PR, red on `main` where the
  classifier fails open). Such tests belong in the vitest suite, not `tests/*.py`.
- **Tests must not write to `~/.hermes/`.** The autouse `_isolate_hermes_home` fixture in
  `tests/conftest.py` redirects `HERMES_HOME`; never hardcode `~/.hermes/` in tests. Profile
  tests also mock `Path.home()` so `_get_profiles_root()` / `_get_default_hermes_home()` stay
  in the temp dir (pattern: `tests/hermes_cli/test_profiles.py`):
  ```python
  @pytest.fixture
  def profile_env(tmp_path, monkeypatch):
      home = tmp_path / ".hermes"; home.mkdir()
      monkeypatch.setattr(Path, "home", lambda: tmp_path)
      monkeypatch.setenv("HERMES_HOME", str(home))
      return home
  ```
  Tests that `patch.object(Path, "home", ...)` must ALSO set `HERMES_HOME` — code reads the
  env var, not `Path.home()/.hermes`.

### Don't fake the host OS

Behaviour that genuinely differs per host is tested ON that host with `@pytest.mark.linux_only`
/ `macos_only` / `windows_only`, never by patching `sys.platform`. Host-independent things stay
unmarked: pure functions that take the platform as data (`hidden_windows_child_options(opts,
is_windows=True)`) and declaration/packaging invariants ("pyproject declares `tzdata` with a
`sys_platform == 'win32'` marker"). Setting a module-level `IS_WINDOWS` flag and calling
`windows_detach_flags()` IS a fake. The line: **if the test needs the interpreter to believe it
is on another OS to pass, it belongs on that OS.** A test that walks several platforms in
sequence is split — host-native arm on Linux, other arms as their own marked tests.

**Use the marker, never a bare `skipif`.** `scripts/ci/list_os_marked_tests.py` finds files for
the macOS/Windows lanes by grepping the marker *name*, then filters with `-m <marker>`. A
`skipif(sys.platform != "win32")` test skips on Linux AND is never imported on Windows — it runs
nowhere, silently. A file-local alias (`windows_only = pytest.mark.skipif(...)`) is listed but
`-m windows_only` deselects everything: green over zero coverage. Don't `pytest.skip()` non-host
rows of a platform `@parametrize` — split into one marked test per OS.

**Live Windows process-topology E2E (`wine2e` lane):** `windows-venv-e2e.yml` runs
`tests/hermes_cli/test_venv_holder_windows_live.py` on a real `windows-latest` runner (real
processes, no mocked psutil) ONLY on pushes to `wine2e/**` branches. Workflow: write probes
pinning CORRECT behavior, push to `wine2e/` to reproduce live on unfixed code, fix, iterate to
green, then open the PR with the live receipt. Extend it when touching that subsystem; assert
against the gateway ANCESTOR found by argv, not the direct parent (the venv shim makes every
spawn a launcher/worker chain).

### Don't write change-detector tests

A change-detector fails whenever data *expected to change* is updated — model catalogs,
`_config_version`, enumeration counts, hardcoded model lists. It adds no coverage and taxes
every routine update. Don't: `assert "gemini-2.5-pro" in _PROVIDER_MODELS["gemini"]`,
`assert DEFAULT_CONFIG["_config_version"] == 21`, `assert len(models) == 8`. Do: `assert
"gemini" in _PROVIDER_MODELS and len(_PROVIDER_MODELS["gemini"]) >= 1` (plumbing works);
`assert raw["_config_version"] == DEFAULT_CONFIG["_config_version"]` (migration reaches
latest); `assert not (set(moonshot_models) & coding_plan_only_models)` (no leak); every
catalog model has a context-length entry (relationship). If it reads like a snapshot, delete
it; if it reads like a contract between two pieces of data, keep it. Reviewers reject new
change-detectors; authors convert them before re-review.

### Never read source code in tests

A test that reads a `.py`/`.ts`/`.tsx` file's text tests the *shape of the source*, not
behavior — banned outright. It passes when the implementation is subtly broken (regex matches
a mis-wired call site) and fails on correct refactors; it can't run against bundled/minified
artifacts; it blocks structural cleanup; it gives false confidence. Don't
`fs.readFileSync('main.ts')` + `assert.match(source, /spawn\(...hiddenWindowsChildOptions/)`.
Do extract the logic into a pure/DI-testable function and call it:
```ts
export function hiddenWindowsChildOptions(options = {}, isWindows = process.platform === 'win32') {
  if (!isWindows || 'windowsHide' in options) return options
  return { ...options, windowsHide: true }
}
```
If the logic lives inline in a god-file and extraction feels disruptive, that is the signal to
extract, not to regex around it.

## Routing Table — working in X → read X/AGENTS.md

| Area | Read | Covers |
|---|---|---|
| `run_agent.py`, `agent/` | `agent/AGENTS.md` | AIAgent + mixins, turn phases, caching integrity, message-flow invariants, compression, model/aux resolution |
| `cli.py`, `hermes_cli/`, `main.py` | `hermes_cli/AGENTS.md` | CLI mixins, `_SLASH_DISPATCH`, slash registry, config system + loaders, skins, `hermes update` pipeline, profiles / multiplex |
| `gateway/` | `gateway/AGENTS.md` | Adapters, two message guards, streaming contract, background notifications, gateway vs desktop lifecycle, token locks, scoped secrets |
| `tools/`, `toolsets.py`, `model_tools.py` | `tools/AGENTS.md` | Adding tools, registry, toolsets, delegation, cross-tool references, backends |
| `plugins/`, `hermes_cli/plugins*.py` | `plugins/AGENTS.md` | Plugin kinds, native compat contract, in-tree policy, Sep-2026 compat window |
| `tui_gateway/`, `ui-tui/` | `tui_gateway/AGENTS.md` | Process model, JSON-RPC transport, key surfaces, slash flow, dev commands |
| `web/`, `hermes_cli/web_routers/` | `web/AGENTS.md` | Dashboard embeds the real TUI; what React may and may not rebuild |
| `apps/desktop/` | `apps/desktop/AGENTS.md`, `apps/desktop/src/AGENTS.md` | Desktop judgment guide; `serve` backend, slash palette curation, Bot Mode canonical chat |
| `skills/`, `optional-skills/`, `agent/curator*.py` | `skills/AGENTS.md` | Frontmatter, HARDLINE authoring standards, curator |
| `cron/`, kanban (`hermes_cli/kanban*.py`, `tools/kanban_tools.py`, `plugins/kanban/`) | `cron/AGENTS.md` | Scheduler invariants, job fields, kanban board/dispatcher |
| `gateway/platforms/` new adapter | `gateway/platforms/ADDING_A_PLATFORM.md` | Step-by-step adapter guide |

Long-form background lives in `website/docs/developer-guide/` (agent-loop, prompt-assembly,
context-compression-and-caching, gateway-internals, tools-runtime, plugins/, cron-internals,
session-storage, ...). Workflow rules (PR/issue/review/salvage process) live in the
`hermes-agent-dev` skill, not here.


## Host-local runtime preservation contracts

5. **Codex message phases have one delivery owner.** Completed commentary
   `agentMessage` items remain interim candidates because a later tool may
   still follow. A completed `phase=final_answer` item is terminal, so its
   deltas may animate the draft but the item itself must bypass the interim
   callback and let the turn finalizer persist the answer once. Phase-less
   items stay on the legacy interim path. Exact
   `has_delivered_text(final_response)` identity remains a fallback for older
   producers that cannot distinguish phases; unrelated commentary never
   suppresses the final because its text does not match.


### Codex app-server process retirement must preserve the thread
Codex app-server is stateful even though Hermes may retire its subprocess
after a timeout, watchdog event, gateway restart, or update. Persist the
model-scoped thread id in the Hermes session before closing the process and
use `thread/resume` in its replacement. If Codex no longer has the rollout,
seed the fresh thread with a bounded transcript from canonical Hermes history;
never continue with only the newest Telegram message.

The per-turn timeout is an inactivity bound, not an absolute wall-clock cap:
refresh it on every in-scope app-server notification or server request so a
productive tool-heavy turn can continue past ten minutes. Only
`turn/completed`, or a matching terminal turn returned by
`thread/read(includeTurns=true)`, proves the turn finished. An
`item/completed` `agentMessage` proves only that one message item finished;
Codex can emit several progress messages in the same turn. Never promote one
to a successful final response merely because a deadline elapsed. If stored
turn state is still running or cannot be proved terminal, interrupt, return a
partial failure, retire the process, and preserve its thread for recovery.
Do not enable a shorter post-tool silence watchdog by default: after a large
tool result, Codex can legitimately spend more than 90 seconds reasoning with
no new item notification. Explicitly bounded callers may still opt into that
stricter watchdog; the normal path relies on the general inactivity bound.

Context overrides are also subprocess launch policy: a profile-owned
`model.context_length` must reach app-server as Codex CLI config, while the
effective window reported by live token-usage events is display/accounting
state, not the next launch request. Codex `cachedInputTokens` is a subset of
`inputTokens`, not an additional prompt bucket. Profiles that explicitly own
context policy show only real model slugs; synthetic `-900k` picker aliases
remain available only when context policy is not pinned. The combined
regression contour lives in
`tests/run_agent/test_codex_app_server_integration.py`.

The `/model` confirmation must retain that profile-owned large-context policy
for a session-only switch between compatible `openai-codex` models, such as
gpt-6-astra to gpt-5.6-terra. Do not display Codex's 272K catalogue
advertisement in that case: it is not the selected app-server launch policy.
Other providers and Codex models without a verified large-context path must
continue to resolve their own context limit.


## Completion policy parity

Normal and Codex app-server conversations support the generic `pre_turn_complete`
hook for material decisions with no file mutations. One optional continuation is
allowed; interrupts/errors never produce successful completion receipts. The
Codex current input includes the same composed plugin/prefetch context as its
persisted api_content sidecar. `pre_api_request` on this transport explicitly
uses request_scope=runtime_turn, not an assertion about internal model requests.
Preserve clean user content, durable thread continuity and single final delivery.


## Update recovery discipline — 2026-09-06

The Sep 6 update stopped before code changes because the maintained branch was
dirty. Preserve reviewed code in commits and keep runtime/camera `evidence/`
ignored. Retain `updates.parked_branch_strategy: update_in_place`; do not switch
production to main or discard stashes to bypass the gate. Stage upstream merges
in a separate worktree and run host-local continuity/context/plugin regressions.
See docs/UPDATE_RECOVERY_2026-09-06.md for primary logs and recovery state.

Обновление Hermes 0.21.0 активировано на коммите 1792e07e3a51c722fd265b0013998cab2b7dceff; живая проверка подтверждений в Telegram после обновления ещё не завершена. Активация подтверждена 2026-09-07 в 02:07 UTC: PID2742508/start115184664, Telegram connected от этого writer, maintained branch `fix/codex-context-continuity-20260829`. Последующий documentation-only commit не меняет startup code stamp и не требует перезапуска. [Source: /root/.local/state/hermes-update-repair-20260906/activation-20260907/activation-status.json; live systemd/proc/Git readback, 2026-09-07]

CLI и gateway используют `.hermes-runtime/venv-update-20260907`, editable source — production. Проверены Python3.11.15/SQLite3.53.1 и 152 совместимых пакета; прежние shared venv сохранены. Реальный model+terminal canary после установки вернул HERMES_UPDATE_NATIVE_OK: api_mode=codex_responses, nested Codex session=false. Подтверждены compression.threshold=0.75, approvals.mode=manual/timeout900/cron_mode=deny; вложенный Codex не включался. [Source: activation-20260907/postactivation-direct-runtime.log; direct-runtime-receipt.json; CLI/uv/config/import readback, 2026-09-07]

Повторный committed-tree прогон: 59 файлов/917 passed/0 failed; TUI/web собраны и чистая offline-установка этих workspace проверена до финальной остановки gateway. Исполняемый код совпадает с e6761a8045, включая чувствительные absolute-home redirects и binding native approval к request/chat/message/choice. Финальная версия installer прошла 18 ad-hoc guard/retry тестов. Полный broad suite не green и не объявляется принятой полной проверкой. Все 7 профильных backup-каталогов последней активации проверены: SQLite quick_check=ok и приватные режимы файлов. [Source: activation-20260907/retry-committed-tests.log; ui-preflight-receipt.json; postactivation-verification.json; real ad-hoc pytest result, 2026-09-07]

Повторная проверка Hermes 7 сентября 2026 подтвердила активированный runtime и сохранённые локальные правки: 938 тестов в 61 файле прошли без ошибок и пропусков. Approval timeout 900 секунд сохранён, но подагент прервал ожидавший approval по общему лимиту 600 секунд; этот конфликт был и в preupdate config. Человеческий approve/deny round-trip не принят. [Source: /root/hermes-agent-fix-20260811/docs/UPDATE_AUDIT_2026-09-07.md; /root/.local/state/audit-digest-hermes-20260907/tests/summary.json; live journal/config readback; User, 2026-09-07]

История попыток: ожидание закончилось без установки в01:29; два последующих rollback сохранили прежний source/runtime. Исправлены критерий остановки (inactive/failed разрешены только при MainPID0 и пустом cgroup), scoped npm install для ui-tui/web вместо Electron/Desktop, возврат на maintained branch и уникальный backup-каталог каждой попытки. Предыдущие receipts/backups сохранены. Новый запуск существующего installer после успеха не разрешён автоматически: pins относятся к историческому preactivation PID/HEAD. [Source: activation-20260907/activation-attempt1-timeout-status.json; activation-attempt2-stop-rollback.json; activation-attempt3-ui-rollback.json; activate_when_idle.py, 2026-09-07]

Датированный аудит до ремонта подтвердил обычный Telegram turn и tools, но обнаружил конфликт child deadline/approval wait, неисправный checkpoint store и старые ошибки адаптеров. Последующее разрешённое устранение описано в актуальном разделе ниже; ранний аудит не является текущим статусом этих неисправностей. [Source: docs/UPDATE_AUDIT_2026-09-07.md; User, 2026-09-07]

## Operations repair — activated 2026-09-07

Исправления Hermes 9937337c4fde853a100d0a57483fb8031a79a6db активированы 7 сентября 2026 в14:02:55UTC (17:02:55МСК), новый gateway PID516146. Живая проверка17:48UTC подтвердила ожидаемый код и его хеши, Telegram/main HA connected, отсутствие дублирующих HA-адаптеров, checkpoint fsck, авторизованный Notion MCP и12/12 целевых тестов. Approval остаётся manual/900секунд, вычислительный бюджет подагента600секунд. Дополнительный перезапуск для активации не нужен. [Source: /root/hermes-agent-fix-20260811/docs/OPS_REPAIR_2026-09-07.md; /root/.local/state/hermes-ops-repair-20260907/postactivation-receipt.json; postactivation-tests.log; live systemd/config readback, 2026-09-07]

Keep approvals manual/900s and the child's600s execution budget; exclude only owner-scoped bounded human waits. Checkpoint recovery preserved213original files and passed safe snapshot/restore; the final preactivation regression was69files/1110passed, not a full broad-suite claim. HAtools/voice services and secrets remain intact; only duplicate event adapters are disabled. Next optional acceptance is a real human Telegram approve/deny round-trip; it is not a prerequisite to the already-proven activation. Do not restart again for documentation-only updates. [Source: User; docs/OPS_REPAIR_2026-09-07.md; live postactivation receipt, 2026-09-07]

## Maintained-install update hygiene

Keep task diagnostics out of installed source. The default gateway profile uses
explicit `terminal.cwd: /root`: a multiplex terminal scope drops placeholder `.`
and otherwise the local tool falls back to the systemd installation cwd. Private
DM dumps belong outside the checkout, mode0600; the root-only legacy dump ignore
rule must not be widened to unknown source files. Preserve the dirty-tree guard
and `parked_branch_strategy: update_in_place`. See `docs/UPDATE_HYGIENE.md` for
reproduction, private preservation and update acceptance boundaries.

## Codex progress and steering incident — 2026-09-06

2026-09-06: подтверждён ложный abort Codex-хода через 600 секунд (last activity: starting new turn), потому что app-server event bridge не обновлял AIAgent activity clock. Исправлен bridge: реальные события обновляют _touch_activity независимо от UI. AIAgent.steer теперь направляет Codex-коррекции в native turn/steer, а rejection/no session возвращает False для очереди gateway. В default config agent.turn_liveness.timeout_s=0; настройка проверена через реальный resolver. 121 связанных тестов прошли; дополнительная gateway→AIAgent→Codex-session→protocol проверка прошла в наборе из 6 тестов. systemctl reload запросил штатный restart после активного хода; новый PID и живая доставка steering в Telegram пока не проверены. Не считать патч активированным до смены PID. Следующий шаг после завершения этого хода: проверить новый gateway PID и доставку коррекции во время живого хода.

Evidence: /root/hermes-agent-fix-20260811/evidence/liveness-steer-20260906. Code: agent/codex_runtime.py and run_agent.py; regressions in tests/run_agent/test_steer.py, tests/agent/test_codex_runtime_live_events.py, tests/gateway/test_steer_command.py. Native Codex owns its tool loop: never claim steer accepted into the Hermes-only pending queue. Real provider events must reach the shared activity clock.


## Hermes direct runtime and Codex approvals repair — applied 2026-09-06

**Штатный runtime Hermes активирован и проверен.** `model.openai_runtime=auto` при `provider=openai-codex` выбирает `codex_responses`: новый Telegram-session после reload обслуживается собственным `agent.conversation_loop` Hermes, а не вложенным Codex app-server. Сохранены настроенная OpenAI-модель, OAuth, `approvals.mode=manual`, `timeout=900` и `cron_mode=deny`. Direct Responses smoke вернул `HERMES_DIRECT_OK` 2026-09-06 22:28:39 UTC; gateway был заново поднят в 22:33:11 UTC, а следующий Telegram-ход начался позднее. Бинарник Codex, плагины и credentials не удалялись; opt-in runtime остаётся доступным.

**Ремонт opt-in Codex app-server approvals принят в live checkout.** Он направляет запросы исполнения/изменения файлов в штатную очередь Hermes, перечитывает актуальный approval mode на каждый запрос, разрешает только `once`/`deny` и привязывает Telegram callback к request ID, chat ID, message ID и предложенным вариантам. Missing UI, send error, timeout, interruption, foreign/stale callback и отсутствие listener закрываются отказом. Применение прошло clean/reverse patch checks; новейший focused suite на final tree дал `115 passed in 17.37s` (подготовленный изолированный patch ранее проходил `144/144`). Repo-wide suite не принят как evidence: он начал массово падать из-за удаления временного `HERMES_HOME/logs` в e2e-окружении и был остановлен, не выдаваясь за regression result.

**Штатная Telegram approval-кнопка проверена в direct runtime.** Безопасный probe `chmod 777` был направлен на заранее подтверждённый несуществующий path. Hermes запросил `world/other-writable permissions`, пользователь выбрал `Run once`, команда ожидаемо завершилась `No such file or directory`, а повторная проверка подтвердила отсутствие target. Это подтверждает реальный одноразовый gateway approval round-trip без изменения файлового состояния.

**Hopper canary установлен.** `/etc/cron.d/pearl-allocation-canary` и state под `/var/lib/pearl-hopper-monitor/allocation-canary-20260906` созданы 2026-09-06 22:48:17 UTC. Реальный cron tick добавил вторую успешную пробу в 22:50:01 UTC; reader занял 18.17 ms, новых allocation/OOM-событий в пробе нет. Два ранее разрешённых отчёта запланированы на 23:48:17 UTC 2026-09-06 и 22:48:17 UTC 2026-09-07; успешные отправки дедуплицируются, failed send повторяется, после обоих отчётов sampling прекращается. Связи [[projects/pearl-hopper]], [[projects/gbrain]].
