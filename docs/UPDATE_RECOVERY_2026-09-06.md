# Hermes update recovery — 2026-09-06

## Cause and preservation boundary

The operator reported the latest update failed. The actual update ran at
2026-09-06T22:18:57Z..22:27:08Z and stopped before modifying code, dependencies,
or restarting services. `logs/update.log` and
`logs/update_receipts/update_20260906_222708_1142489.json` record exit 1 and
`CODE UPDATE SKIPPED`: the parked production branch
`fix/codex-context-continuity-20260829` had uncommitted changes. HEAD stayed
`1eba8db2e73654f8aae4551bdbfcb61195f7d220`.

The configured `updates.parked_branch_strategy: update_in_place` was already
correct. The dirty-tree gate runs before that strategy; changing to main or
bypassing the guard would not be a safe repair. Keep the maintained branch and
all local committed fixes, preserve uncommitted work before integrating upstream.

## Recovery in progress

- Freshly fetched upstream target: `693641aa8b4359c602283bdbbc14041e03bc47bc`.
- Existing watchdog/activity and native steering changes were reviewed without
  changing their behavior. The focused pre-integration suite passed 87 tests.
- The existing approvals-repair draft remains NOT applied; the runtime switch
  and unrelated permission policies are out of this update's mutation scope.
- Pre-recovery source diff, SHA-256 manifest and tar archive of source/evidence
  are in `/root/.local/state/hermes-update-repair-20260906/` (private).
- Keep `evidence/` local-only: it contains a camera capture as well as runtime
  receipts. Never publish the evidence directory to clean the working tree.
- Original update backups and all historical stashes are retained.

## Repeatable maintenance rule

Before `hermes update`, check `git status --short` in the live source checkout.
Commit reviewed code + tests + runbook together; keep runtime captures ignored.
Retain `updates.parked_branch_strategy: update_in_place`. Do not use
`--switch-branch`, reset to upstream, or discard old stashes to clear this gate.
Test an upstream merge away from production, including host-local regressions.
Only claim activation after fresh runtime version/PID evidence and smoke tests.
