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

## Current recovery status — dated source readback 2026-09-06 23:42 UTC

The update is NOT deployed. The original reviewed work was preserved in
`666d5bd3b608af8cc58e69792501cc66587cfbf5`. The separate staging worktree
`/root/worktrees/hermes-update-recovery-20260906`, branch
`integration/update-recovery-20260906`, contains upstream
`693641aa8b4359c602283bdbbc14041e03bc47bc` via merge
`6ec8417e0fc1be707425b26114fc327d57d354c0` and verification-doc commit
`7a59ab749b7efebeb76a94c4d7cfab0cc1615c01`. Staging is clean.
[Source: local Git readback 2026-09-06; private recovery HANDOFF.md]

The separate approvals repair IS now committed in production code baseline
`a4944d5940fc835982daf1f8f9cd57a15dfc25c3`; the production checkout was clean at
2026-09-06T23:42:58Z. It is not an ancestor of staging7a59ab749b. Waiting for the
other owner to create a commit is therefore no longer the blocker. The next step
is coordinated source preservation/review against the exact latest production
commit, then tests of the direct Hermes loop and shared Telegram approval buttons,
followed by a separately verified direct-runtime activation. Nested Codex
app-server is NOT required and must not be enabled as an update prerequisite;
the operator explicitly clarified this on2026-09-07. Keep existing shared approval
protections; no removal of committed opt-in code or credentials was requested.
[Source: User correction and readonly config/runtime resolver, 2026-09-07]
Docs-only commits after this snapshot do not change that
code baseline or prove the resident gateway loaded it.
[Source: Git log/status/show and merge-base --is-ancestor exit1,
2026-09-06T23:42:58Z; docs/CODEX_APPROVAL_REPAIR_2026-09-06.md]

Final saved staging verification:17files,288tests passed,0failed; TUI/web builds
succeeded. The broad run was NOT green:45,373passed,143failed,380skipped and one
no-result timed-out file. Four observed failures were subsequently fixed or
validated in the focused run; the remaining139failure identifiers reproduced on
pinned pure upstream with the same Python. None of this accepts an approvals
merge that has not happened, nor a provider/runtime smoke. The delayed workers'
22:51timeouts are historical partial-work evidence, not new failures or completed
independent reviews.
[Source: /root/.local/state/hermes-update-repair-20260906/verification-summary.json,
final-focused.log and upstream-baseline logs; worker transcripts deleg_d991f47f;
2026-09-06]

Current upkeep is documentation/source maintenance only: no application code,
dependencies, configuration, service restart, deployment or rollback is performed.
Preserve the working permission policy and do not infer gateway activation from a
clean Git checkout. [Source: User source-maintenance scope, 2026-09-06]

## Historical preservation phase — 2026-09-06 22:40 UTC

At the initial preservation phase, the approvals repair was an unapplied draft;
it was later applied/committed by a separate task, as recorded above. The original
watchdog/activity and native steering pre-integration baseline passed87tests.
Pre-recovery source diff, SHA-256 manifest and source/evidence tar remain private
under `/root/.local/state/hermes-update-repair-20260906/`. Runtime/camera evidence
stays ignored; original update backups and historical stashes remain retained.
[Source: original recovery records and preservation commit666d5bd3b6,
2026-09-06]

## Repeatable maintenance rule

Before `hermes update`, check `git status --short` in the live source checkout.
Commit reviewed code + tests + runbook together; keep runtime captures ignored.
Retain `updates.parked_branch_strategy: update_in_place`. Do not use
`--switch-branch`, reset to upstream, or discard old stashes to clear this gate.
Test an upstream merge away from production, including host-local regressions.
Only claim activation after fresh runtime version/PID evidence and smoke tests.
