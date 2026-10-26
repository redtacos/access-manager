import uuid
import logging
from typing import List
from src.connectors import ConnectorFactory
from src.run_report import ProcessingReport, ProcessingStep, ProcessingResult
from src.repositories import RequestRepository, GrantRepository, TargetRepository
from src.models import AccessRequest, AccessGrant, AccessGrantStatus, AccessTargetApprovalMethod

logger = logging.getLogger(__name__)


class AccessService:

    def __init__(self):
        self.request_repo = RequestRepository()
        self.grant_repo = GrantRepository()
        self.target_repo = TargetRepository()


    def process_pending_requests(self) -> List[ProcessingReport]:
        pending_requests = self.request_repo.get_pending_requests()
        return [self._process_pending_request(request) for request in pending_requests]

    def _process_pending_request(self, request: AccessRequest) -> ProcessingReport:
        try:
            target = self.target_repo.get_active_target_by_id(request.target_id)

            if target.approval_method == AccessTargetApprovalMethod.AUTO:
                self.request_repo.approve_request(request.id, 'system')
                return ProcessingReport.ok(request, ProcessingStep.REQUEST_ROUTING, ProcessingResult.NO_ACTION_NEEDED)
            elif target.approval_method == AccessTargetApprovalMethod.OWNERS:
                self.request_repo.change_request_to_pending_approval(request.id)
                return ProcessingReport.ok(request, ProcessingStep.REQUEST_ROUTING, ProcessingResult.APPROVAL_REQUIRED)
            elif target.approval_method == AccessTargetApprovalMethod.SPECIAL:
                # TODO: Implement the special process approval. Until then, report it (never auto-approve it).
                return ProcessingReport.failed(request, ProcessingStep.REQUEST_ROUTING, 'Special process approval is not implemented yet')
            else:
                logger.error(f'Invalid AccessTargetApprovalMethod encountered for request {request.id} ({target.approval_method})')
                return ProcessingReport.failed(request, ProcessingStep.REQUEST_ROUTING, f'Invalid AccessTargetApprovalMethod ({target.approval_method})')

        except Exception as e:
            logger.error(f'Error encountered for pending request {request.id} ({e})')
            return ProcessingReport.failed(request, ProcessingStep.REQUEST_ROUTING, str(e))


    def process_approved_requests(self) -> List[ProcessingReport]:
        approved_requests = self.request_repo.get_approved_requests()
        return [self.process_approved_request(request) for request in approved_requests]

    def process_approved_request(self, request: AccessRequest) -> ProcessingReport:
        try:
            grant = AccessGrant(
                id=uuid.uuid4(),
                request_id=request.id,
                user_id=request.user_id,
                target_id=request.target_id,
                status=AccessGrantStatus.PENDING,
                ends_on=request.ends_on
            )

            # TODO: The 2 next calls should be wrapped in a transaction
            self.grant_repo.create_grant(grant)
            self.request_repo.complete_request(request.id)

            return ProcessingReport.ok(request, ProcessingStep.CREATE_GRANT, ProcessingResult.NOTIFICATION_REQUIRED)

        except Exception as e:
            logger.error(f'Error encountered for approved request {request.id} ({e})')
            return ProcessingReport.failed(request, ProcessingStep.CREATE_GRANT, str(e))


    def process_pending_grants(self) -> List[ProcessingReport]:
        pending_grants = self.grant_repo.get_pending_grants()
        return [self.process_pending_grant(grant) for grant in pending_grants]

    def process_pending_grant(self, grant: AccessGrant) -> ProcessingReport:
        try:
            target = self.target_repo.get_active_target_by_id(grant.target_id)

            connector = ConnectorFactory.get_connector(target.system)
            success = connector.provision_grant(grant, target)

            if success:
                self.grant_repo.activate_grant(grant.id)
                return ProcessingReport.ok(grant, ProcessingStep.PROVISION_GRANT, ProcessingResult.NOTIFICATION_REQUIRED)
            else:
                logger.error(f'Error encountered when provisioning grant {grant.id}')
                return ProcessingReport.failed(grant, ProcessingStep.PROVISION_GRANT, f'Error encountered when provisioning grant')
        except Exception as e:
            logger.error(f'Error encountered for pending grant {grant.id} ({e})')
            return ProcessingReport.failed(grant, ProcessingStep.PROVISION_GRANT, str(e))


    def process_expired_grants(self) -> List[ProcessingReport]:
        expired_grants = self.grant_repo.get_expired_grants()
        return [self.process_expired_grant(grant) for grant in expired_grants]

    def process_expired_grant(self, grant: AccessGrant) -> ProcessingReport:
        try:
            target = self.target_repo.get_active_target_by_id(grant.target_id)

            connector = ConnectorFactory.get_connector(target.system)
            success = connector.deprovision_grant(grant, target)

            if success:
                self.grant_repo.revoke_grant(grant.id, 'system')
                return ProcessingReport.ok(grant, ProcessingStep.REVOKE_GRANT, ProcessingResult.NOTIFICATION_REQUIRED)
            else:
                logger.error(f'Error encountered when deprovisioning grant {grant.id}')
                return ProcessingReport.failed(grant, ProcessingStep.REVOKE_GRANT, f'Error encountered when deprovisioning grant')
        except Exception as e:
            logger.error(f'Error encountered for expired grant {grant.id} ({e})')
            return ProcessingReport.failed(grant, ProcessingStep.REVOKE_GRANT, str(e))
