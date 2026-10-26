'''AccessManager: orchestration only, the services are replaced by mocks.'''
from unittest.mock import MagicMock

import pytest

from src import access_manager as access_manager_module
from src.access_manager import AccessManager
from src.run_report import ProcessingReport, ProcessingResult, ProcessingStep, RunReport
from tests.factories import make_request

STEPS = [
    'process_pending_requests',
    'process_approved_requests',
    'process_pending_grants',
    'process_expired_grants',
]


def report_for(step_name):
    return ProcessingReport.ok(
        make_request(), ProcessingStep.REQUEST_ROUTING, ProcessingResult.NO_ACTION_NEEDED
    )


@pytest.fixture
def manager(monkeypatch):
    calls = []
    access_service, notification_service = MagicMock(), MagicMock()
    results = {}
    for name in STEPS:
        results[name] = report_for(name)

        def step(name=name):
            calls.append(name)
            return [results[name]]

        setattr(access_service, name, step)

    def send(report):
        calls.append('notify')

    notification_service.send_report_notifications.side_effect = send
    monkeypatch.setattr(access_manager_module, 'AccessService', lambda: access_service)
    monkeypatch.setattr(access_manager_module, 'NotificationService', lambda: notification_service)

    instance = AccessManager()
    instance.calls, instance.results = calls, results
    instance.access_service, instance.notification_service = access_service, notification_service
    return instance


def test_steps_run_in_order_and_notifications_are_sent_last(manager):
    manager.run()

    assert manager.calls == STEPS + ['notify']


def test_the_report_contains_the_results_of_every_step(manager):
    report = manager.run()

    assert isinstance(report, RunReport)
    assert report.results == [manager.results[name] for name in STEPS]


def test_notifications_are_sent_once_with_the_complete_report(manager):
    report = manager.run()

    manager.notification_service.send_report_notifications.assert_called_once_with(report)


def test_a_step_that_crashes_is_reported_and_the_following_steps_still_run(manager):
    def crash():
        manager.calls.append('process_approved_requests')
        raise RuntimeError('database unreachable')

    manager.access_service.process_approved_requests = crash

    report = manager.run()

    assert manager.calls == STEPS + ['notify']
    [failure] = report.failures
    assert failure.subject is None
    assert 'database unreachable' in str(failure.error)
    assert len(report.results) == len(STEPS)  # 3 healthy steps + 1 crash


def test_notifications_are_still_sent_when_a_step_crashes(manager):
    manager.access_service.process_pending_grants = MagicMock(side_effect=RuntimeError('boom'))

    manager.run()

    manager.notification_service.send_report_notifications.assert_called_once()


def test_a_run_with_nothing_to_do_still_returns_an_empty_report(manager):
    for name in STEPS:
        setattr(manager.access_service, name, lambda: [])

    report = manager.run()

    assert report.results == []
    assert report.failures == []
