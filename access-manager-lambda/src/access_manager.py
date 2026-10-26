import logging
from .services import AccessService, NotificationService
from .run_report import RunReport, ProcessingReport, ProcessingStep

logger = logging.getLogger(__name__)


class AccessManager:

    def __init__(self):
        self.access_service = AccessService()
        self.notification_service = NotificationService()

    def run(self) -> RunReport:
        report = RunReport()
        steps = [
            (ProcessingStep.REQUEST_ROUTING, self.access_service.process_pending_requests),
            (ProcessingStep.CREATE_GRANT, self.access_service.process_approved_requests),
            (ProcessingStep.PROVISION_GRANT, self.access_service.process_pending_grants),
            (ProcessingStep.REVOKE_GRANT, self.access_service.process_expired_grants),
        ]
        try:
            for processing_step, step in steps:
                report.extend(self._run_step(processing_step, step))
        finally:
            self.notification_service.send_report_notifications(report)
        return report

    def _run_step(self, processing_step, step):
        try:
            return step()
        except Exception as e:
            logger.critical(f'Step {processing_step.name} failed, encountered exception {e}')
            return [ProcessingReport.failed(None, processing_step, f'{processing_step.name}: {e}')]
