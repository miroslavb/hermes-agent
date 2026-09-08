# Hermes maintained-install update hygiene

## Current repair — 2026-09-08

The 22:27 UTC updater run stopped at the parked-branch dirty-tree guard, before any source change. Its receipt retained pre/post `5c691d36b98bb30a49b32f2dd1be04363ec8ce8c`, exit1. The only untracked path was a private `telegram_dm_snapshot_*.json` diagnostic. [Source: User, 2026-09-08; logs/update.log; logs/update_receipts/update_20260908_223243_418315.json; live git status]

The gateway starts with WorkingDirectory at the install checkout. Under multiplexing, the per-profile terminal scope discards placeholder `cwd: .` and does not inherit the process-global gateway home fallback; the local terminal resolver then uses the process working directory. A real profile-scope read from that directory reproduced this installation-path default. [Source: gateway/run.py:_profile_runtime_scope; tools/terminal_scope.py:build_profile_terminal_scope; tools/terminal_tool.py:_resolve_cwd; live scope probe, 2026-09-08]

Default profile `terminal.cwd` is now explicitly `/root`. A source-directory launch plus the real scoped resolver returns `/root`; a structural before/after YAML comparison proves that only this field changed. The existing diagnostic was moved without byte changes to private mode0600 evidence outside the checkout. A narrowly root-anchored Git ignore rule prevents legacy DM dump filenames from entering commits/autostashes. Unknown source files and tracked edits still block the updater; the guard and `updates.parked_branch_strategy: update_in_place` remain intact. [Source: /root/.local/state/hermes-update-repair-20260908/preservation.json; config.before.yaml; live scope/config readback; regression tests, 2026-09-08]

## Continuing policy

- Keep installed source for code, tests and runbooks. Put private task diagnostics under the profile logs/workspace or `/root/.local/state/`, with directories0700 and private files0600. Never publish raw chat snapshots.
- Default gateway terminal cwd must be an explicit absolute workspace, not the systemd installation WorkingDirectory. Other profiles retain their independent policy; this repair does not change them.
- Do not disable the dirty-tree guard, autocommit unknown files, use `--switch-branch`, or reset maintained patches to clear SKIPPED.
- Before integrating upstream, pin both commits and run `git merge-tree`. A clean status only clears the dirt gate; it does not prove conflict-free integration, dependency compatibility, or runtime activation.
- Run `scripts/run_tests.sh` for the parked-branch and terminal-scope contracts. Require an exact new update receipt and runtime readback before claiming a completed update.

## Verification boundary

The original dirty guard reproduced `(False, 'dirty')`; after preserving the sole diagnostic, it admitted the maintained branch `(True, 'unmerged:18')`. The new private-artifact regression failed before the ignore rule. Full upstream integration and activation are separate acceptance work, not established by these checks. Private evidence: `/root/.local/state/hermes-update-repair-20260908/`. [Source: actual guard probes and red.log, 2026-09-08]
