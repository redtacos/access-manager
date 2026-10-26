'''NotificationService: who gets told what, and how many messages they get.'''
from src.models import NotificationType
from src.run_report import ProcessingReport, ProcessingResult, ProcessingStep, RunReport
from tests.factories import make_grant, make_request


def run_report(*reports):
    run = RunReport()
    run.extend(list(reports))
    return run


def approval_needed(request=None):
    return ProcessingReport.ok(
        request or make_request(), ProcessingStep.REQUEST_ROUTING, ProcessingResult.APPROVAL_REQUIRED
    )


def user_event(step, subject=None):
    return ProcessingReport.ok(
        subject or make_request(), step, ProcessingResult.NOTIFICATION_REQUIRED
    )


class TestApprovalRequests:
    def test_an_approver_gets_a_single_message_for_all_their_requests(self, notification_service, outbox):
        first, second = make_request(user_id='alice'), make_request(user_id='bob')

        notification_service.send_report_notifications(
            run_report(approval_needed(first), approval_needed(second))
        )

        [message] = outbox.to('owner-1')
        assert 'alice' in message and 'bob' in message
        assert len(outbox.messages) == 1

    def test_every_approver_of_a_request_is_notified(self, notification_service, outbox):
        outbox.approvers = ['owner-1', 'owner-2']

        notification_service.send_report_notifications(run_report(approval_needed()))

        assert len(outbox.to('owner-1')) == 1
        assert len(outbox.to('owner-2')) == 1

    def test_each_notification_is_recorded_per_request_and_approver(self, notification_service, outbox):
        outbox.approvers = ['owner-1', 'owner-2']
        request = make_request()

        notification_service.send_report_notifications(run_report(approval_needed(request)))

        recorded = [c.args[0] for c in notification_service._repo.create_notification.call_args_list]
        assert {(n.user_id, n.request_id, n.type) for n in recorded} == {
            ('owner-1', request.id, NotificationType.APPROVAL_REQUEST),
            ('owner-2', request.id, NotificationType.APPROVAL_REQUEST),
        }

    def test_a_notification_that_could_not_be_sent_is_not_recorded_and_others_still_go_out(
        self, notification_service, outbox
    ):
        outbox.approvers = ['owner-1', 'owner-2']
        outbox.failing_recipients = {'owner-1'}

        notification_service.send_report_notifications(run_report(approval_needed()))

        assert outbox.to('owner-1') == []
        assert len(outbox.to('owner-2')) == 1
        recorded = [c.args[0] for c in notification_service._repo.create_notification.call_args_list]
        assert [n.user_id for n in recorded] == ['owner-2']


class TestUserMessages:
    def test_a_user_gets_a_single_message_for_everything_that_changed(self, notification_service, outbox):
        approved = user_event(ProcessingStep.CREATE_GRANT, make_request(user_id='alice'))
        granted = user_event(ProcessingStep.PROVISION_GRANT, make_grant(user_id='alice'))

        notification_service.send_report_notifications(run_report(approved, granted))

        [message] = outbox.to('alice')
        assert 'approved' in message.lower()
        assert 'granted' in message.lower()
        assert len(outbox.messages) == 1

    def test_each_user_gets_their_own_message(self, notification_service, outbox):
        notification_service.send_report_notifications(run_report(
            user_event(ProcessingStep.PROVISION_GRANT, make_grant(user_id='alice')),
            user_event(ProcessingStep.REVOKE_GRANT, make_grant(user_id='bob')),
        ))

        assert 'granted' in outbox.to('alice')[0].lower()
        assert 'revoked' in outbox.to('bob')[0].lower()
        assert len(outbox.messages) == 2

    def test_a_denied_request_is_announced_as_denied(self, notification_service, outbox):
        notification_service.send_report_notifications(run_report(
            user_event(ProcessingStep.REQUEST_DENIED, make_request(user_id='alice')),
        ))

        assert 'denied' in outbox.to('alice')[0].lower()

    def test_users_are_not_told_about_failures(self, notification_service, outbox):
        failure = ProcessingReport.failed(
            make_grant(user_id='alice'), ProcessingStep.PROVISION_GRANT, 'Okta is down'
        )

        notification_service.send_report_notifications(run_report(failure))

        assert outbox.to('alice') == []

    def test_one_unreachable_user_does_not_stop_the_others(self, notification_service, outbox):
        outbox.failing_recipients = {'alice'}

        notification_service.send_report_notifications(run_report(
            user_event(ProcessingStep.PROVISION_GRANT, make_grant(user_id='alice')),
            user_event(ProcessingStep.PROVISION_GRANT, make_grant(user_id='bob')),
        ))

        assert len(outbox.to('bob')) == 1


class TestErrorReport:
    def test_a_run_without_failures_sends_nothing_to_the_iam_team(self, notification_service, outbox):
        notification_service.send_report_notifications(run_report())

        assert outbox.messages == []

    def test_all_failures_are_bundled_in_one_message_to_the_iam_team(self, notification_service, outbox):
        grant, request = make_grant(), make_request()

        notification_service.send_report_notifications(run_report(
            ProcessingReport.failed(grant, ProcessingStep.PROVISION_GRANT, 'Okta returned 500'),
            ProcessingReport.failed(request, ProcessingStep.REQUEST_ROUTING, 'target not found'),
            ProcessingReport.ok(make_request(), ProcessingStep.REQUEST_ROUTING, ProcessingResult.NO_ACTION_NEEDED),
        ))

        [message] = outbox.to(notification_service._iam_team_recipient)
        assert 'Okta returned 500' in message
        assert 'target not found' in message
        assert str(grant.id) in message
        assert str(request.id) in message
        assert len(outbox.messages) == 1

    def test_a_crashed_step_without_a_subject_is_still_reported(self, notification_service, outbox):
        crash = ProcessingReport.failed(None, ProcessingStep.PROVISION_GRANT, 'process_pending_grants: boom')

        notification_service.send_report_notifications(run_report(crash))

        [message] = outbox.to(notification_service._iam_team_recipient)
        assert 'boom' in message


class TestResilience:
    def test_sending_notifications_never_raises(self, notification_service, outbox):
        outbox.failing_recipients = {'owner-1', 'alice', notification_service._iam_team_recipient}

        notification_service.send_report_notifications(run_report(
            approval_needed(),
            user_event(ProcessingStep.PROVISION_GRANT, make_grant(user_id='alice')),
            ProcessingReport.failed(make_grant(), ProcessingStep.PROVISION_GRANT, 'boom'),
        ))

        assert outbox.messages == []
