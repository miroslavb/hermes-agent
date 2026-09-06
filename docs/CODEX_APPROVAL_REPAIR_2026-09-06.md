# Codex → Hermes approvals: tested draft, application blocked

The operator explicitly requested repair after enabling Hermes manual approvals.
The production routing code, Codex reviewer config and gateway process were not
changed in this repair task. Two attempts to change the live routing code were
rejected by auto_review, including the exact tested patch. The reviewer classified
conversation authorization as untrusted transcript content. Do not repeat the
same user-consent question or apply the patch through an alternative path.

## Verified defects

1. Codex runtime obtained only the CLI thread-local callback. A real AIAgent
   regression with a registered gateway listener reproduced callback=None.
2. Hermes bypass flags were captured at Codex session creation, so a reused
   transport could retain an old mode after /approvals changed.
3. Telegram bound cards to a session and resolved FIFO. A real adapter/queue
   test reproduced an expired card approving a NEW queued request.

## Proposed repair

repair.patch and manifest.json contain the exact reviewed scope. The isolated
copy is review/. It routes pending exec/fileChange requests through the shared
Hermes queue, checks current mode/listener per request, and offers only once/deny.
It binds Telegram cards to request ID, chat, message ID and offered choices.
Missing UI, send errors, timeout, interruption and foreign/stale responses deny.
CLI retains its registered prompt path; unattended manual contexts deny.
Existing explicit off/yolo preference semantics remain request-scoped; no real
config was edited and no runtime rejection is overridden by the patch.

## Evidence

- final-tests.txt: 144 passed in 24.41 seconds in an isolated checkout.
- telegram-baseline.txt: old card resolved the new command (reproduced).
- combined-tests.txt and boundary-tests.txt: intermediate focused checks.
- Tests exercise real queue + Codex protocol + Telegram adapter/callback.
  Network/SDK card boundary and policy source are test doubles; live Telegram
  delivery and a real app-server approval round trip were not exercised.
- Production checkout no longer contains the deliberately failing reproduction;
  the standalone patch includes it and its final passing form.
- The patch does not modify Codex auto_review or permission configuration.

## Remaining work

Application needs acceptance by the governing approval mechanism. Once permitted,
apply this exact scope with manifest checks; activate through the standard
idle/drain gateway reload and verify a real native approval/denial round trip.
The separate Codex auto_review can still reject before any UI request exists;
this UI repair does not claim to reverse that decision. Hopper cron and its two
reports remain uninstalled/unscheduled under the earlier explicit authorization.
Sources: projects/hermes-agent, projects/pearl-hopper, infra/host-map.


## Runtime architecture clarification

**Штатный runtime Hermes — настройка применена 2026-09-06 22:28 UTC; активация gateway после текущего ответа.** По прямому запросу оператора выполнена штатная команда hermes config set model.openai_runtime auto. Сохранены provider=openai-codex, модель по умолчанию gpt-5.6-terra, существующий OAuth, approvals.mode=manual, timeout=900 и cron_mode=deny. Настройки разрешений самого Codex не менялись. Реальный resolver выбрал codex_responses (source=device_code); короткий прямой Responses-запрос к настроенному OpenAI на gpt-5.6-terra без инструментов успешно вернул HERMES_DIRECT_OK, проверка 22:28:39 UTC. Текущий ответ ещё выполняется в ранее запущенном Codex; для новых агентов предусмотрен штатный reload gateway через SIGUSR1 с ожиданием завершения активной работы. Полный Telegram-ход с историей и инструментами пока не принят. Бинарник Codex, плагины и учётные данные сохранены. Патч ремонта Codex→Hermes approvals не применён; дефект устаревших Telegram-кнопок отдельно не исправлен. Cron и два отчёта Hopper пока не установлены. Следующий шаг: завершить штатную активацию, проверить следующий Telegram-ход и продолжить ранее разрешённую задачу Hopper при действующих подтверждениях. Доказательства: /root/.local/state/codex-approval-repair-20260906/direct-runtime-smoke.json и runtime-switch-state.md; config readback; hermes_cli/codex_runtime_switch.py, hermes_cli/runtime_provider.py, gateway/run.py:12864 и /etc/systemd/system/hermes-gateway.service. Связи [[projects/pearl-hopper]], [[projects/gbrain]].
