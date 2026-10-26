'''AccessService with its repositories and connector replaced by mocks.'''
from unittest.mock import MagicMock

import pytest

from src.connectors import ConnectorFactory
from src.models import AccessGrantStatus, AccessTargetApprovalMethod
from src.run_report import ProcessingReport, ProcessingResult, ProcessingStep
from src.services import AccessService
from src.services import access_service as access_service_module
from tests.factories import make_grant, make_request, make_target, utcnow


@pytest.fixture
def service(monkeypatch):
    for name in ('RequestRepository', 'GrantRepository', 'TargetRepository'):
        monkeypatch.setattr(access_service_module, name, MagicMock)
    return AccessService()


@pytest.fixture
def connector(monkeypatch):
    fake = MagicMock()
    fake.provision_grant.return_value = True
    fake.deprovision_grant.return_value = True
    monkeypatch.setitem(ConnectorFactory._connectors, 'Okta', fake)
    return fake


class TestProcessPendingRequests:
    def route(self, service, request, approval_method):
        service.request_repo.get_pending_requests.return_value = [request]
        service.target_repo.get_active_target_by_id.return_value = make_target(
            id=request.target_id, approval_method=approval_method
        )
        return service.process_pending_requests()

    def test_nothing_pending_means_nothing_to_report(self, service):
        service.request_repo.get_pending_requests.return_value = []
        assert service.process_pending_requests() == []

    def test_auto_approved_targets_are_approved_by_the_system(self, service):
        request = make_request()
        [report] = self.route(service, request, AccessTargetApprovalMethod.AUTO)

        request_id, approved_by = service.request_repo.approve_request.call_args.args
        assert request_id == request.id
        assert approved_by.lower() == 'system'
        service.request_repo.change_request_to_pending_approval.assert_not_called()
        assert report.succeeded
        assert report.processing_step == ProcessingStep.REQUEST_ROUTING
        assert report.processing_step_result == ProcessingResult.NO_ACTION_NEEDED

    def test_owner_approved_targets_wait_for_an_approver(self, service):
        request = make_request()
        [report] = self.route(service, request, AccessTargetApprovalMethod.OWNERS)

        service.request_repo.change_request_to_pending_approval.assert_called_once_with(request.id)
        service.request_repo.approve_request.assert_not_called()
        assert report.succeeded
        assert report.processing_step_result == ProcessingResult.APPROVAL_REQUIRED
        assert report.subject == request

    def test_special_process_requests_are_never_auto_approved(self, service):
        request = make_request()
        [report] = self.route(service, request, AccessTargetApprovalMethod.SPECIAL)

        service.request_repo.approve_request.assert_not_called()
        # Whatever the outcome, the run must get a report it can work with
        # (not None), so the IAM team can see it.
        assert isinstance(report, ProcessingReport)

    def test_a_target_that_cannot_be_loaded_is_reported_and_leaves_the_request_alone(self, service):
        request = make_request()
        service.request_repo.get_pending_requests.return_value = [request]
        service.target_repo.get_active_target_by_id.side_effect = LookupError('no such target')

        [report] = service.process_pending_requests()

        assert not report.succeeded
        assert report.processing_step == ProcessingStep.REQUEST_ROUTING
        assert 'no such target' in str(report.error)
        service.request_repo.approve_request.assert_not_called()
        service.request_repo.change_request_to_pending_approval.assert_not_called()

    def test_one_broken_request_does_not_stop_the_others(self, service):
        broken, healthy = make_request(), make_request()
        service.request_repo.get_pending_requests.return_value = [broken, healthy]
        service.target_repo.get_active_target_by_id.side_effect = [
            RuntimeError('database hiccup'),
            make_target(approval_method=AccessTargetApprovalMethod.OWNERS),
        ]

        first, second = service.process_pending_requests()

        assert not first.succeeded and first.subject == broken
        assert second.succeeded and second.subject == healthy
        service.request_repo.change_request_to_pending_approval.assert_called_once_with(healthy.id)


class TestProcessApprovedRequests:
    def test_an_approved_request_becomes_a_pending_grant_and_is_completed(self, service):
        request = make_request(ends_on=utcnow(), user_id='alice')
        service.request_repo.get_approved_requests.return_value = [request]

        [report] = service.process_approved_requests()

        grant = service.grant_repo.create_grant.call_args.args[0]
        assert grant.request_id == request.id
        assert grant.user_id == 'alice'
        assert grant.target_id == request.target_id
        assert grant.ends_on == request.ends_on
        assert grant.status == AccessGrantStatus.PENDING
        service.request_repo.complete_request.assert_called_once_with(request.id)
        assert report.succeeded
        assert report.processing_step == ProcessingStep.CREATE_GRANT
        assert report.processing_step_result == ProcessingResult.NOTIFICATION_REQUIRED

    def test_every_request_gets_its_own_grant(self, service):
        service.request_repo.get_approved_requests.return_value = [make_request(), make_request()]

        reports = service.process_approved_requests()

        grants = [call.args[0] for call in service.grant_repo.create_grant.call_args_list]
        assert len(reports) == len(grants) == 2
        assert grants[0].id != grants[1].id

    def test_a_request_is_not_completed_when_its_grant_could_not_be_created(self, service):
        request = make_request()
        service.request_repo.get_approved_requests.return_value = [request]
        service.grant_repo.create_grant.side_effect = RuntimeError('write failed')

        [report] = service.process_approved_requests()

        assert not report.succeeded
        assert report.processing_step == ProcessingStep.CREATE_GRANT
        assert 'write failed' in str(report.error)
        service.request_repo.complete_request.assert_not_called()


class TestProcessPendingGrants:
    def setup_grant(self, service, system='Okta'):
        grant = make_grant()
        target = make_target(id=grant.target_id, system=system)
        service.grant_repo.get_pending_grants.return_value = [grant]
        service.target_repo.get_active_target_by_id.return_value = target
        return grant, target

    def test_a_successful_provisioning_activates_the_grant(self, service, connector):
        grant, target = self.setup_grant(service)

        [report] = service.process_pending_grants()

        connector.provision_grant.assert_called_once_with(grant, target)
        service.grant_repo.activate_grant.assert_called_once_with(grant.id)
        assert report.succeeded
        assert report.processing_step == ProcessingStep.PROVISION_GRANT
        assert report.processing_step_result == ProcessingResult.NOTIFICATION_REQUIRED

    def test_a_refusal_from_the_target_system_leaves_the_grant_pending(self, service, connector):
        grant, _ = self.setup_grant(service)
        connector.provision_grant.return_value = False

        [report] = service.process_pending_grants()

        assert not report.succeeded
        assert report.processing_step == ProcessingStep.PROVISION_GRANT
        service.grant_repo.activate_grant.assert_not_called()

    def test_an_exception_from_the_connector_is_reported(self, service, connector):
        self.setup_grant(service)
        connector.provision_grant.side_effect = RuntimeError('Okta exploded')

        [report] = service.process_pending_grants()

        assert not report.succeeded
        assert 'Okta exploded' in str(report.error)
        service.grant_repo.activate_grant.assert_not_called()

    def test_a_target_on_an_unsupported_system_is_reported(self, service, connector):
        self.setup_grant(service, system='Mainframe')

        [report] = service.process_pending_grants()

        assert not report.succeeded
        assert 'Unsupported system type' in str(report.error)
        service.grant_repo.activate_grant.assert_not_called()

    def test_one_failing_grant_does_not_stop_the_others(self, service, connector):
        bad, good = make_grant(), make_grant()
        service.grant_repo.get_pending_grants.return_value = [bad, good]
        service.target_repo.get_active_target_by_id.return_value = make_target()
        connector.provision_grant.side_effect = [False, True]

        first, second = service.process_pending_grants()

        assert not first.succeeded and first.subject == bad
        assert second.succeeded and second.subject == good
        service.grant_repo.activate_grant.assert_called_once_with(good.id)


class TestProcessExpiredGrants:
    def setup_grant(self, service):
        grant = make_grant(status=AccessGrantStatus.ACTIVE, ends_on=utcnow())
        target = make_target(id=grant.target_id)
        service.grant_repo.get_expired_grants.return_value = [grant]
        service.target_repo.get_active_target_by_id.return_value = target
        return grant, target

    def test_an_expired_grant_is_removed_from_the_system_and_revoked(self, service, connector):
        grant, target = self.setup_grant(service)

        [report] = service.process_expired_grants()

        connector.deprovision_grant.assert_called_once_with(grant, target)
        grant_id, revoked_by = service.grant_repo.revoke_grant.call_args.args
        assert grant_id == grant.id
        assert revoked_by.lower() == 'system'
        assert report.succeeded
        assert report.processing_step == ProcessingStep.REVOKE_GRANT
        assert report.processing_step_result == ProcessingResult.NOTIFICATION_REQUIRED

    def test_a_grant_stays_active_when_the_removal_fails(self, service, connector):
        self.setup_grant(service)
        connector.deprovision_grant.return_value = False

        [report] = service.process_expired_grants()

        assert not report.succeeded
        assert report.processing_step == ProcessingStep.REVOKE_GRANT
        service.grant_repo.revoke_grant.assert_not_called()

    def test_an_exception_from_the_connector_is_reported(self, service, connector):
        self.setup_grant(service)
        connector.deprovision_grant.side_effect = RuntimeError('timeout')

        [report] = service.process_expired_grants()

        assert not report.succeeded
        assert 'timeout' in str(report.error)
        service.grant_repo.revoke_grant.assert_not_called()
