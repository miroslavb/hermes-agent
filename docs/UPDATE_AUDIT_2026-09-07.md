# Post-reconciliation update audit — 2026-09-07

## Result

Production Hermes 0.21.0 is actually activated, not merely present in the checkout. Read-only audit of the running gateway confirms PID 2742508 / start ticks 115184664, system start 02:06:42 UTC and startup code stamp `1792e07e3a51c722fd265b0013998cab2b7dceff`. Current maintained branch is `fix/codex-context-continuity-20260829`. Audit-start HEAD `27920673e3632d39faafa130a3115561240d4b57` differs from reviewed executable baseline `e6761a8045d95852ee96528e2f593c19ca553d25` only in AGENTS.md and the recovery runbook. [Source: live systemctl/proc/gateway_state.json and Git checks, 2026-09-07 12:44–12:45 UTC]

Git ancestry preserves all three required milestones: upstream `693641aa8b4359c602283bdbbc14041e03bc47bc`, local work preservation `666d5bd3b608af8cc58e69792501cc66587cfbf5`, and approval repair `a4944d5940fc835982daf1f8f9cd57a15dfc25c3`. No tracked working-tree changes existed before this documentation audit. [Source: three successful git merge-base --is-ancestor checks, git status and diff, 2026-09-07]

Both CLI and gateway resolve `.hermes-runtime/venv-update-20260907`, Python 3.11.15 / SQLite 3.53.1, editable imports from production. Fresh `uv pip check` inspected 152 packages and reported all compatible. The maintained settings remain direct native Hermes (`codex_responses` in the saved postactivation canary, no nested Codex acceptance requirement), compression threshold 0.75 and manual approval policy. The current live conversation has exercised model responses and harmless tools; it does not substitute for a button approval/deny round-trip. [Source: live interpreter/import/dependency checks; activation direct-runtime receipt; current operator conversation; config readback, 2026-09-07]

## Fresh regression evidence

Re-ran the 59-file committed activation regression list plus two turn-liveness suites in fresh per-file pytest processes with the actual gateway interpreter and isolated HERMES_HOME. Result: **61 files / 938 tests passed / 0 failures / 0 errors / 0 skipped**, 52.1 seconds wall time. The list covers native response integration, approval request identity/routing/redaction, Telegram callbacks, steering, event bridge, continuity/context, completion hooks, updates and sensitive absolute-home writes. Each file's exit status and JUnit report are preserved privately. This is a focused regression pass, not full-suite green or a live Telegram human approval test. [Source: /root/.local/state/audit-digest-hermes-20260907/tests/summary.json and per-file JUnit XML, 2026-09-07]

The earlier 917-test activation result and broad-suite failures remain historical evidence in UPDATE_RECOVERY_2026-09-06.md; this audit neither reran nor accepted the entire broad suite. TUI/web build receipts were read as saved activation evidence, not fresh rebuilds. [Source: saved activation receipts and audit scope, 2026-09-07]

## Existing issues, not new update regressions

- Auto-checkpoint operations still fail `git add -A` with `fatal: not a git repository: '/root/.hermes/checkpoints/store'`. The same signature exists under old PID 1207263 before activation and new PID 2742508. A fresh read-only Git repository probe fails too. This checkpoint store was not repaired by this audit. [Source: PID-scoped journal comparison and git --git-dir read-only probe, 2026-09-07]
- The duplicate Home Assistant credential failures in secondary profile adapters occur under both old and new PIDs. Notion reconnect failures and other MCP/network warnings remain; this audit does not certify every adapter healthy or authorize changing other profiles. [Source: PID-scoped journals, gateway platform state, 2026-09-07]
- A startup warning said systemd stop timeout was 90 seconds. The actual loaded manager value is now 330 seconds (`5min 30s`), so that startup warning is not a current timeout defect. No unexpected systemd restarts: NRestarts=0 at audit. [Source: systemctl show hermes-gateway.service, 2026-09-07]

## Approval cancellation during this audit

The operator reported missing the approval button and recalled the intended 900-second timeout. Both current config and `config.yaml.preupdate` contain `approvals.timeout=900`, `delegation.child_timeout_seconds=600`, and `subagent_auto_approve=false`. The timeout setting was preserved; the earlier overall child deadline defeats the requested human waiting window. [Source: User, 2026-09-07; read-only current/preupdate YAML comparison]

The child hit its 600-second deadline at12:46:24.075UTC. At12:46:24.924 the approval waiter logged `Approval wait interrupted by user signal — returning deny`; a later callback at12:48:36.991 resolved zero approvals. The child tool had waited375.88seconds, not900. The user did not explicitly deny: worker cancellation was mapped to a deny outcome. The late click cannot authorize a closed request. No retry or approval-policy change was made. Fix scope should reconcile child lifetime and human waiting time rather than simply reapplying900 or weakening approval controls. [Source: tools/approval_gateway_wait.py:161–167; agent.log and PID2742508 journal, 2026-09-07]

## Scope and next step

No software update, install, restart, rollback, permission change, profile modification or Telegram test-send was performed. Only documentation and source-grounded memory records are maintained. Do not replay the historical activation installer: its pins refer to preactivation identities. [Source: current user verification request and action log, 2026-09-07]

Remaining acceptance: a separate harmless native Telegram approve/deny round-trip with exact message/request identity, one final delivery and session continuation. The known checkpoint-store fault needs a separate bounded preservation-first repair; do not delete/reinitialize it just to clear this audit. [Source: current audit limits and existing errors, 2026-09-07]

Private evidence directory: `/root/.local/state/audit-digest-hermes-20260907/`. The independent reader did not return a completed final audit; the reported final tests, ancestry, service state and error comparisons were executed by the primary agent. [Source: primary tool output and worker transcript, 2026-09-07]
