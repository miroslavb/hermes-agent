# Hermes update recovery — 2026-09-06

## Established cause

The operator reported the latest update failed. The actual update ran at
2026-09-06T22:18:57Z..22:27:08Z and stopped before modifying code, dependencies,
or restarting services. `logs/update.log` and
`logs/update_receipts/update_20260906_222708_1142489.json` record exit 1 and
`CODE UPDATE SKIPPED`: the parked production branch
`fix/codex-context-continuity-20260829` had uncommitted changes. HEAD stayed
`1eba8db2e73654f8aae4551bdbfcb61195f7d220`.

`updates.parked_branch_strategy: update_in_place` was already correct. The
dirty-tree gate precedes that strategy. Switching to main or bypassing the
safety check is not the repair.

## Recovery and preservation

- Reviewed local source, tests and docs were preserved in commit
  `666d5bd3b608af8cc58e69792501cc66587cfbf5`; the exact branch ref was read back
  from `fork`. The pre-recovery diff, source/evidence tar and SHA manifest are
  private under `/root/.local/state/hermes-update-repair-20260906/`.
- Runtime/camera `evidence/` remains ignored, not published. Original backups
  and historical stashes remain intact.
- Pinned upstream `693641aa8b4359c602283bdbbc14041e03bc47bc` was merged in
  `/root/worktrees/hermes-update-recovery-20260906`, branch
  `integration/update-recovery-20260906`, away from production.
- Upstream decomposed the old facades. Local behavior was ported into the real
  phase modules: Codex continuity and context policy, native steering,
  request observation, plugin context, bounded completion policy, and exact-text
  final delivery suppression.
- Regression checks caught missing delegated context/turn ID, an unreachable
  native completion hook, no-session steering recursion, and mutable dispatch
  observation. These were corrected before the final focused run. Config
  context-policy lookup now uses the canonical read-only config API.
- Final focused verification: 17 files, 288 passed, zero failed, canonical
  `scripts/run_tests.sh -j 4`. Exact list and log: `final-focused-files.json` and
  `final-focused.log` in the private evidence directory.
- Staging-only offline npm install and both TUI/web builds succeeded. Build logs:
  `staged-npm-install.log`, `staged-tui-build.log`, `staged-web-build.log`.

## Deployment gate — NOT activated

The broad staging run completed 3,747 files: 45,373 passed, 143 failed,
380 skipped; `test_cmd_update.py` additionally timed out before its result.
This is not a green full suite. Four observed failures were subsequently
resolved/validated by the focused run (the intended Codex sidecar contract,
config read ownership, delegated policy, and temporary unmerged-index duplicate
paths). All remaining 139 broad-run failure identifiers reproduced on pure
upstream in the same Python environment. A longer updater-file retest returned
41 passed / 6 failed on both staging and pure upstream, with identical failing
identifiers. No unclassified integration-only failure remained in this measured
set. This comparison does not turn either full suite green or prove the absence
of real upstream bugs. Evidence: `verification-summary.json` and
`upstream-baseline*.log` in the private receipt directory. The shared production
Python environment was not modified.

A separate active Telegram session is applying and testing Codex/Hermes
approval repairs in production after the baseline commit. Its uncommitted
changes overlap `agent/codex_runtime.py`, transport, gateway, tests and docs.
They are not part of this pinned integration branch. They must be preserved
and merged after that owner finishes; never overwrite them with this branch.
The working gateway remains on its existing process/source. No production
update, dependency replacement, service reload, or activation smoke is claimed.

## Resume safely

1. Confirm the concurrent approvals owner has finished and committed its work.
2. Read fresh production HEAD/status and approvals docs. Integrate that exact
   commit into this staging branch; adapt moved gateway/approval modules rather
   than copying old facades over upstream.
3. Run approval round-trip regressions plus the focused suite and review the
   baseline failure comparison. Resolve any remaining integration-only failure.
4. Rebuild/reinstall only as required by final source, preserving the managed
   SQLite 3.53.1 runtime. Do not repair unrelated dependency pins opportunistically.
5. Deploy only with a stable, clean production tree; verify source SHA, running
   process version, graceful gateway activation and a real smoke before success.

## Repeatable maintenance rule

Before `hermes update`, inspect the live checkout. Commit reviewed code + tests
+ runbook, keep runtime captures ignored, and retain `update_in_place`.
Never reset to upstream, discard stashes, or switch branches merely to silence
the guard. Test maintained-branch integration separately and recheck production
identity/ownership immediately before applying it.
