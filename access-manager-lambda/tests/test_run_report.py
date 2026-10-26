from src.run_report import ProcessingReport, ProcessingResult, ProcessingStep, RunReport
from tests.factories import make_grant, make_request


def ok(result, step=ProcessingStep.REQUEST_ROUTING, subject=None):
    return ProcessingReport.ok(subject or make_request(), step, result)


def failed(step=ProcessingStep.PROVISION_GRANT, error='boom', subject=None):
    return ProcessingReport.failed(subject or make_grant(), step, error)


class TestProcessingReport:
    def test_ok_report_succeeded(self):
        report = ok(ProcessingResult.NO_ACTION_NEEDED)
        assert report.succeeded
        assert report.error is None

    def test_failed_report_carries_its_error(self):
        report = failed(error='Okta is down')
        assert not report.succeeded
        assert report.error == 'Okta is down'
        assert report.processing_step_result == ProcessingResult.ERROR

    def test_subject_can_be_missing_when_a_whole_step_failed(self):
        report = ProcessingReport.failed(None, ProcessingStep.PROVISION_GRANT, 'step crashed')
        assert report.subject is None
        assert not report.succeeded


class TestRunReport:
    def test_extend_accumulates_results_in_order(self):
        run = RunReport()
        first, second, third = (ok(ProcessingResult.NO_ACTION_NEEDED) for _ in range(3))
        run.extend([first])
        run.extend([second, third])
        assert run.results == [first, second, third]

    def test_approvers_are_notified_about_requests_needing_approval(self):
        needs_approval = ok(ProcessingResult.APPROVAL_REQUIRED)
        run = RunReport()
        run.extend([needs_approval, ok(ProcessingResult.NOTIFICATION_REQUIRED)])
        assert run.to_notify_approvers == [needs_approval]

    def test_users_are_notified_about_requests_and_grants_that_changed(self):
        changed = ok(ProcessingResult.NOTIFICATION_REQUIRED, ProcessingStep.PROVISION_GRANT)
        run = RunReport()
        run.extend([changed, ok(ProcessingResult.APPROVAL_REQUIRED)])
        assert run.to_notify_user == [changed]

    def test_failures_are_never_notified_to_users_or_approvers(self):
        run = RunReport()
        run.extend([failed()])
        assert run.to_notify_user == []
        assert run.to_notify_approvers == []

    def test_failures_lists_every_failed_result(self):
        broken_one, broken_two = failed(error='one'), failed(error='two')
        run = RunReport()
        run.extend([ok(ProcessingResult.NO_ACTION_NEEDED), broken_one, broken_two])
        assert run.failures == [broken_one, broken_two]

    def test_empty_report_has_nothing_to_send(self):
        run = RunReport()
        assert run.failures == []
        assert run.to_notify_user == []
        assert run.to_notify_approvers == []
