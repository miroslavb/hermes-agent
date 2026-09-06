# Codex → Hermes approvals: applied and verified

## Current architecture

The default profile now uses `model.openai_runtime: auto`. With the configured
`openai-codex` provider, runtime resolution selects the direct
`codex_responses` path: Hermes owns the agent loop and tools. Codex app-server
is retained only as an opt-in runtime.

The direct OpenAI smoke returned `HERMES_DIRECT_OK` at
2026-09-06 22:28:39 UTC. The gateway entered its new process at 22:33:11 UTC,
and a later Telegram session was observed in `agent.conversation_loop` without
a Codex app-server thread start.

## Repaired defects in the opt-in runtime

1. Codex execution and file-change approval requests now route through the
   shared Hermes runtime approval queue when a gateway listener exists.
2. Approval mode and listener availability are evaluated for every request,
   instead of persisting a bypass decision for the transport lifetime.
3. Telegram approval cards bind to request ID, chat ID, message ID and offered
   choices. Foreign, stale or malformed callbacks cannot resolve a later FIFO
   request.
4. Missing UI, send errors, timeout, interruption, missing listeners and
   invalid responses fail closed. CLI keeps its registered prompt path;
   unattended manual contexts deny.

The patch does not enable Codex app-server, alter Codex `auto_review`, remove
Codex credentials, or broaden an approval beyond the specific request.

## Verification

- Exact prepared patch applied cleanly; reverse-check and `git diff --check`
  passed on the live checkout.
- Newest focused suite on the final live tree: `115 passed in 17.37s`.
  The earlier isolated patch validation had `144/144` passing cases.
- A repo-wide run was not accepted as regression evidence: it began producing
  mass environment-level errors after a temporary `HERMES_HOME/logs` directory
  disappeared and was stopped. This does not replace or weaken the focused
  suite, and it is not reported as a clean full-suite result.
- The suite covers the real queue, Codex protocol, Telegram adapter and callback
  binding. Network/SDK boundaries remain test doubles in those unit tests.
- A real direct-runtime Telegram approval was exercised safely. The target path
  was proved absent, a `chmod 777` request produced the native approval card,
  the operator selected `Run once`, execution returned the expected
  `No such file or directory`, and the target remained absent afterward.

## Hopper follow-through

The separately authorized allocation canary was installed at
2026-09-06 22:48:17 UTC. A real system-cron tick added the second sample at
22:50:01 UTC. The two reports are due at 23:48:17 UTC on 2026-09-06 and
22:48:17 UTC on 2026-09-07. Delivery is deduplicated on success and retried on
failure.

Local evidence remains under
`/root/.local/state/codex-approval-repair-20260906/`. Canonical entities:
`projects/hermes-agent`, `projects/pearl-hopper`, `infra/host-map`.
