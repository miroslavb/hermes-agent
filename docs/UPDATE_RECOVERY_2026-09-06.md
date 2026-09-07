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

## Current recovery status — verified 2026-09-07 01:39 UTC

Обновление Hermes не активировано: 2026-09-07 в 01:29 UTC установщик завершился со статусом blocked_without_install после 30 минут занятого gateway; автоматический повтор запрещён. [Source: /root/.local/state/hermes-update-repair-20260906/activation-20260907/activation-status.json; followup-verification.json, 2026-09-07]

The system activation unit is terminal (`failed`, exit 1, MainPID 0). Its journal
and command log contain the idle-wait timeout, with no install/stop/start/merge
commands. The follow-up did not retry, stop/restart the gateway, change settings,
install packages or enable nested Codex. The later idle snapshot is not permission
to retry. [Source: activation-20260907/followup-installer-journal.txt and
followup-verification.json, 2026-09-07]

Production HEAD before this documentation-only update remains
`1b3708005d3b4b920a527fdb5e9333e66dcfe314`, with a clean checkout. The same gateway
PID `1207263` / start ticks `113903513` is active with startup code stamp
`1eba8db2e73654f8aae4551bdbfcb61195f7d220`, not the candidate. Its cwd is
`/root/hermes-agent-fix-20260811`; ExecStart still uses
`/root/.hermes/hermes-agent/venv/bin/python`. The CLI symlink still targets
`/root/hermes-agent-fix-20260811/.venv/bin/hermes`, and the proposed
`60-update-runtime-20260907.conf` drop-in does not exist. `gateway_state.json`
(snapshot updated 01:34:05 UTC) reports main Telegram connected from that same
writer; this is not a new Telegram round-trip. `hermes --version` and the service
interpreter's actual import resolve the production checkout. A later docs-only
HEAD does not change executable code or the resident process's startup stamp.
[Source: activation-20260907/followup-verification.json; live proc/systemd/CLI/import
readback, 2026-09-07 01:37–01:39 UTC]

The completed candidate is preserved in the separate staging worktree
`/root/worktrees/hermes-update-recovery-20260906`, branch
`integration/update-recovery-20260906`, commit
`e6761a8045d95852ee96528e2f593c19ca553d25`; its fork ref was read back at that exact
SHA. It includes production approvals and upstream
`693641aa8b4359c602283bdbbc14041e03bc47bc`. Its final committed-tree evidence is
59 files / 917 tests passed / 0 failed, plus built TUI/web and a real direct-Hermes
model+terminal canary: `codex_responses`, `HERMES_UPDATE_NATIVE_OK`, tool output
seen, no nested Codex session. These are saved candidate checks, not fresh
production acceptance. The historical broad suite remains non-green; the
139 upstream-reproduced failures are not a full-suite pass.
[Source: activation-20260907/FOLLOWUP.md, committed-tests.log,
direct-runtime-receipt.json and fork ref readback, 2026-09-07]

Read-only configuration check retains `compression.threshold=0.75`,
`model.provider=openai-codex`, `model.openai_runtime=auto`,
`approvals.mode=manual`, `approvals.cron_mode=deny`. The isolated candidate venv
and the old production venvs remain preserved; other profiles were not edited.
The parent backups `config.yaml.preupdate`, `env.preupdate`, `auth.json.preupdate`,
`gateway_state.json.preupdate`, `state.preupdate.db` all match the private
`backup-receipt.json` hashes. The installer never reached its separate
`preactivation-profiles/` backup stage; do not claim those snapshots exist.
[Source: activation-20260907/backup-receipt.json, followup-verification.json and
live read-only config check, 2026-09-07]

Next step: a separately supervised, owner-approved idle activation window. Before
any future attempt, reconcile the candidate with this later documentation-only
production HEAD and review/re-pin OLD/NEW identities; the old installer is not
reusable unchanged. Preserve all commits, stashes, venvs and backups. Only after
actual activation require a new PID/exact code stamp, correct interpreter/imports,
Telegram writer and direct-Hermes/native approval-and-deny round-trip on a harmless
fixture. No post-update human acceptance exists. Nested Codex is neither required
nor enabled. The authorized scope is only the recovery sections in this runbook,
production AGENTS.md and existing default:projects/hermes-agent, plus private
outcome evidence. The unattended write guard refused the AGENTS.md edit; that
protected file remains unchanged and its old recovery subsection is stale. No
alternate write path was attempted. Source upkeep therefore remains explicitly
deferred for the protected primary file, not fully verified. A permitted owner
session must update its recovery subsection to this outcome before a future
activation plan is reviewed. [Source: User bounded follow-up;
activation-20260907/FOLLOWUP.md; protected-file tool rejection, 2026-09-07]

## Historical recovery snapshot — 2026-09-06 23:42 UTC

The following displaced status is preserved as dated history, not the current
candidate or next action.

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
