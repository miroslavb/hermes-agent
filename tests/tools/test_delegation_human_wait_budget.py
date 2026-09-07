"""Human approval time must not consume a delegated child's work budget."""
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from tools import delegate_tool as facade
from tools import delegate_tool_child_run as runs
from tools.approval_human_wait import human_wait_window


def run_child(monkeypatch, work, timeout=0.12):
    finished = threading.Event()
    stopped = []

    def conversation(**kwargs):
        try:
            return work()
        finally:
            finished.set()

    child = SimpleNamespace(
        session_id='approval-test-' + uuid.uuid4().hex,
        run_conversation=conversation,
        get_activity_summary=lambda: {'api_call_count': 1},
    )
    monkeypatch.setattr(facade, '_get_child_timeout', lambda: timeout)
    monkeypatch.setattr(runs, '_signal_child_stop', lambda obj: stopped.append(obj))
    monkeypatch.setattr(runs, '_defer_close_after_timeout', lambda obj, future: None)
    runner = runs._ChildRun(child=child, parent_agent=None, task_index=0,
                           goal='bounded test', subagent_id=None, child_progress_cb=None)
    result = runner.await_child()
    assert finished.wait(2), 'test worker did not terminate'
    return result, stopped


def test_approval_wait_does_not_consume_child_work_budget(monkeypatch):
    def work():
        with human_wait_window('shared-gateway-chat'):
            time.sleep(0.30)
        return {'final_response': 'approved work completed'}

    (result, error, deferred), stopped = run_child(monkeypatch, work)
    assert error is None, 'human waiting was incorrectly charged to child work budget'
    assert result['final_response'] == 'approved work completed'
    assert not stopped
    assert not deferred


def test_nonhuman_blocking_work_still_times_out(monkeypatch):
    def work():
        time.sleep(0.30)
        return {'final_response': 'too late'}

    (result, error, _), stopped = run_child(monkeypatch, work)
    assert result is None
    assert error['status'] == 'timeout'
    assert len(stopped) == 1


def test_another_child_approval_in_same_chat_does_not_extend_budget(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def unrelated_waiter():
        with human_wait_window('shared-gateway-chat'):
            started.set()
            release.wait(2)

    thread = threading.Thread(target=unrelated_waiter)
    thread.start()
    assert started.wait(1)
    try:
        def work():
            time.sleep(0.30)
            return {'final_response': 'too late'}
        (result, error, _), stopped = run_child(monkeypatch, work)
        assert result is None and error['status'] == 'timeout'
        assert len(stopped) == 1
    finally:
        release.set()
        thread.join(2)


@pytest.mark.parametrize('choice', ['once', 'deny'])
def test_real_gateway_wait_resolves_after_child_budget(monkeypatch, choice):
    from tools import approval, approval_context
    from tools.approval_gateway_wait import _await_gateway_decision
    session = 'gateway-budget-' + uuid.uuid4().hex
    timers = []
    resolved = []
    monkeypatch.setattr(approval_context, '_get_approval_timeout', lambda: 2.0)

    def notify(data):
        def answer():
            resolved.append(approval.resolve_gateway_approval(
                session, choice, request_id=data['request_id']))
        timer = threading.Timer(0.90, answer)
        timers.append(timer)
        timer.start()

    def work():
        result = _await_gateway_decision(session, notify, {'command': 'harmless test fixture'})
        return {'final_response': result['choice']}

    try:
        (result, error, _), stopped = run_child(monkeypatch, work, timeout=0.5)
        assert error is None
        assert result['final_response'] == choice
        assert resolved == [1]
        assert not stopped
        assert approval.get_pending_gateway_approval(session) is None
    finally:
        for timer in timers:
            timer.join(2)


def test_wedged_human_window_remains_bounded(monkeypatch):
    from tools import approval_human_wait
    monkeypatch.setattr(approval_human_wait, 'human_wait_ceiling', lambda: 0.04)

    def work():
        with human_wait_window('wedged-' + uuid.uuid4().hex):
            time.sleep(0.30)
        return {'final_response': 'too late'}

    (result, error, _), stopped = run_child(monkeypatch, work)
    assert result is None and error['status'] == 'timeout'
    assert len(stopped) == 1


def test_scope_reaches_context_copied_tool_worker(monkeypatch):
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    def tool():
        with human_wait_window('tool-worker-' + uuid.uuid4().hex):
            time.sleep(0.30)
        return {'final_response': 'tool approved'}

    def work():
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(contextvars.copy_context().run, tool).result()

    (result, error, _), stopped = run_child(monkeypatch, work)
    assert error is None and result['final_response'] == 'tool approved'
    assert not stopped


@pytest.mark.parametrize('timeout', [None, 0.12])
def test_provider_timeout_is_not_reported_as_child_deadline(monkeypatch, timeout):
    def work():
        raise TimeoutError('provider-only timeout')
    (result, error, _), _ = run_child(monkeypatch, work, timeout=timeout)
    assert result is None
    assert error['status'] == 'error'
    assert error['error'] == 'provider-only timeout'
    assert error['timeout_seconds'] is None


def test_parent_cancellation_stops_child_and_defers_close(monkeypatch):
    import asyncio
    from tools import daemon_pool
    real_pool = daemon_pool.DaemonThreadPoolExecutor
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    closed = threading.Event()
    stopped = []
    cancel = asyncio.CancelledError('owner cancelled')

    class CancelPool(real_pool):
        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            def result(timeout=None):
                assert entered.wait(1)
                raise cancel
            future.result = result
            return future

    def work(**kwargs):
        entered.set()
        try:
            release.wait(2)
            return {'final_response': 'stopped fixture'}
        finally:
            finished.set()

    child = SimpleNamespace(session_id='cancel-test-' + uuid.uuid4().hex,
                            run_conversation=work, close=closed.set)
    runner = runs._ChildRun(child=child, parent_agent=None, task_index=0,
                           goal='cancel fixture', subagent_id=None, child_progress_cb=None)
    monkeypatch.setattr(daemon_pool, 'DaemonThreadPoolExecutor', CancelPool)
    monkeypatch.setattr(facade, '_get_child_timeout', lambda: 1.0)
    monkeypatch.setattr(runs, '_signal_child_stop', lambda obj: stopped.append(obj))
    try:
        with pytest.raises(asyncio.CancelledError) as exc:
            runner.await_child()
        assert exc.value is cancel
        assert stopped == [child]
        runner.cleanup(heartbeat=SimpleNamespace(stop=lambda: None),
                       child_pool=None, leased_cred_id=None, close_deferred=False)
        assert not closed.is_set(), 'active worker was closed concurrently'
    finally:
        release.set()
        assert finished.wait(2)
    assert closed.wait(2), 'cancelled worker resources were not closed on completion'
