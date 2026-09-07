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

## Current recovery status — 2026-09-07, prepared activation

The operator authorized completion on 2026-09-07. The exact production baseline
`1b3708005d3b4b920a527fdb5e9333e66dcfe314` is merged into the staging branch,
preserving upstream `693641aa8b4359c602283bdbbc14041e03bc47bc` and shared approvals.
Gateway notifier identity now lives in `gateway/run_turn_runner.py`; the approval
context follows the new `tools.approval_context` canonical module. Both direct
Hermes and retained opt-in runtime are covered. Default remains direct
`codex_responses`, not nested Codex. [Source: Git merge/diff and tests,
2026-09-07; User authorization, 2026-09-07]

Combined acceptance in the isolated candidate environment: 59 files, 917 passed,
0 failed. TUI and web builds pass; compatibility-pointer check passes. An actual
Hermes model/tool loop returned `HERMES_UPDATE_NATIVE_OK` after a successful
terminal tool call; `api_mode=codex_responses`, no Codex subprocess session.
The first canary returned a housekeeping summary instead of the exact marker;
the preserved second run passed without disabling the housekeeping hook.
[Source: activation-20260907/candidate-tests.log, tui-build.log, web-build.log,
direct-runtime-attempt1.json and direct-runtime-receipt.json, 2026-09-07]

A real upstream security defect was reproduced and fixed before activation:
a one-component absolute POSIX home such as `/root` was not normalized, allowing
sensitive absolute SSH redirects to miss detection. Targeted RED/GREEN and the
complete selected approval suite now pass. Do not classify this as an accepted
upstream failure. [Source: approval-upstream-baseline.log, home-normalization-red.log,
home-normalization-green.log and candidate-tests.log, 2026-09-07]

Candidate environment: `.hermes-runtime/venv-update-20260907`, locked Python
3.11.15 / SQLite 3.53.1, 152 installed packages, `uv pip check` clean. Teams is
not configured on served profiles; its optional MSAL extra conflicts with the
upstream cryptography pin and is not included in this runtime. Other live venvs
and their consumers remain unchanged. TUI workspace is `ui-tui`, not `tui`.
[Source: candidate-install-final.log and fresh interpreter/dependency checks,
2026-09-07]

The owner separately raised `compression.threshold` to `0.75` in the default
profile. Readback confirmed 0.75. It is captured at AIAgent initialization, so
an already-running CLI agent may retain the prior value; new agents use 75%.
Other compression settings and approval/provider policy are unchanged.
[Source: User and `hermes config set` / load_config_readonly readback, 2026-09-07]

Production is NOT yet activated. Another Telegram turn is active, so activation
must wait for idle rather than interrupt it. Keep the prepared commit and run a
bounded, identity-guarded installer only after the gateway drains. Verify the new
PID/start-time, exact loaded commit, direct runtime and connected Telegram;
a post-update human approval round-trip is still required. Rollback preserves
old commits, settings and venvs. [Source: gateway state/process/log readback,
2026-09-07; activation acceptance boundary]

Private primary evidence and rollback inputs are in
`/root/.local/state/hermes-update-repair-20260906/activation-20260907/`.
The main SQLite session backup passed quick_check. Do not publish settings,
credentials, database copies or raw transcripts.
[Source: backup-receipt.json, 2026-09-07]

## Historical staging status — 2026-09-06

The pre-approvals staging commit `7a59ab749b` passed 288 targeted tests.
The old broad run was NOT green: remaining 139 failure identifiers reproduced
on pinned upstream. Those results do not replace today's final selected-tree
acceptance and are not a full-suite PASS. Original logs and summaries are
preserved in the private recovery directory. [Source: verification-summary.json,
2026-09-06]

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

Before `hermes update`, inspect the live checkout. Commit reviewed code + tests
+ runbook, keep runtime captures ignored, and retain `update_in_place`.
Never reset to upstream, discard stashes, or switch branches merely to silence
the guard. Test maintained-branch integration separately and recheck production
identity/ownership immediately before applying it.
