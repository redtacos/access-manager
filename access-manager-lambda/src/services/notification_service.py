import uuid
import logging
from datetime import datetime, timezone
from typing import List
from collections import defaultdict
from src.models import Notification, NotificationType, AccessRequest, AccessGrant, AccessTarget
from src.repositories import NotificationRepository
from src.run_report import RunReport, ProcessingReport, ProcessingStep, ProcessingResult

logger = logging.getLogger(__name__)


class NotificationService:

    def __init__(self):
        self._iam_team_recipient = 'IAM TEAM' # TODO: Replace when the notification channel is implemented
        self._repo = NotificationRepository()

    def send_report_notifications(self, report: RunReport) -> None:
        try:
            self._send_approval_request([r for r in report.to_notify_approvers])
            self._send_user_messages([r for r in report.to_notify_user])
            self._send_error_report(report.failures)
        except Exception:
            logger.exception('Could not send the notifications')

    def _send_approval_request(self, results: List[ProcessingReport]) -> None:
        by_approver = defaultdict(list)
        for result in results:
            for approver in self._find_approvers(result.subject):
                by_approver[approver].append(result)

        for approver, results in by_approver.items():
            try:
                self._send_notification(approver, self._build_approval_request_message(results))
                self._record_approval_notifications(approver, results)
            except Exception:
                logger.exception('Could not notify %s', approver)

    def _send_user_messages(self, results: List[ProcessingReport]) -> None:
        by_user = defaultdict(list)
        for result in results:
            by_user[result.subject.user_id].append(result)

        for user, results in by_user.items():
            try:
                self._send_notification(user, self._build_user_message(results))
                # TODO: Should we record notifications sent to users?
            except Exception:
                logger.exception('Could not notify %s', user)

    def _send_error_report(self, results: List[ProcessingReport]) -> None:
        if not results:
            return
        try:
            self._send_notification(self._iam_team_recipient, self._build_error_report_message(results))
            # TODO: Should we record notifications sent to users?
        except Exception:
            logger.exception('Could not send the error report to the IAM team')

    def _find_approvers(self, request: AccessRequest) -> List[str]:
        # TODO: Implement a way to retreive all owners/approvers for the target of the request
        return ['Mr. Approver']

    def _build_approval_request_message(self, results: List[ProcessingReport]) -> str:
        # TODO: Craft a better message, this is only a PoC
        message_lines = ['Some users have requested access to systems you own, please review the following requests and record a decision.']
        for result in results:
            message_lines.append(f'User {result.subject.user_id} has requested access to {result.subject.target_id}. Please record your decision here: LINK TO SPA')
        return '\n'.join(message_lines)

    def _build_user_message(self, results: List[ProcessingReport]) -> str:
        # TODO: Craft a better message, this is only a PoC
        message_lines = ['Some of your access requests/grants have changed, see details below.']
        for result in results:
            if result.processing_step == ProcessingStep.CREATE_GRANT:
                message_lines.append(f'Your request for access to {result.subject.target_id} has been approved. See your request here: LINK TO SPA')
            elif result.processing_step == ProcessingStep.REQUEST_DENIED:
                message_lines.append(f'Your request for access to {result.subject.target_id} has been denied. See your request here: LINK TO SPA')
            elif result.processing_step == ProcessingStep.PROVISION_GRANT:
                message_lines.append(f'Your access to {result.subject.target_id} has been granted. See your grant here: LINK TO SPA')
            elif result.processing_step == ProcessingStep.REVOKE_GRANT:
                message_lines.append(f'Your access to {result.subject.target_id} has been revoked. See your grant here: LINK TO SPA')
        return '\n'.join(message_lines)

    def _build_error_report_message(self, results: List[ProcessingReport]) -> str:
        # TODO: Craft a better message, this is only a PoC
        message_lines = ['Some errors were encountered during the last Access Manager run, see details below.']
        for result in results:
            if result.processing_step in [ProcessingStep.REQUEST_ROUTING, ProcessingStep.CREATE_GRANT, ProcessingStep.REQUEST_DENIED]:
                message_lines.append(f'Request {result.subject} encountered the following error during step {result.processing_step}: {result.error}')
            elif result.processing_step in [ProcessingStep.PROVISION_GRANT, ProcessingStep.REVOKE_GRANT]:
                message_lines.append(f'Grant {result.subject} encountered the following error during step {result.processing_step}: {result.error}')
        return '\n'.join(message_lines)

    def _record_approval_notifications(self, approver: str, results: List[ProcessingReport]) -> None:
        for result in results:
            self._repo.create_notification(
                Notification(
                    id=uuid.uuid4(),
                    request_id=result.subject.id,
                    user_id=approver,
                    sent_on=datetime.now(timezone.utc),
                    type=NotificationType.APPROVAL_REQUEST,
                )
            )

    def _send_notification(self, recipient, message):
        # TODO: Implement a notification channel (Slack/Email/etc.)
        pass
