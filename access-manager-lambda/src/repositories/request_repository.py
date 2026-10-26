import uuid
import logging
from typing import List
from datetime import datetime, timezone
from botocore.exceptions import ClientError

from src.dynamo_db_utils import get_resource
from src.models import AccessRequest, AccessRequestStatus

logger = logging.getLogger(__name__)


class RequestRepository:

    def __init__(self):
        self._table = get_resource().Table('AccessRequest')

    def create_request(self, request: AccessRequest) -> None:
        try:
            self._table.put_item(Item=request.to_dict())
            logger.info(f'Created new request {request.id}')
        except ClientError as e:
            logger.error(f'Error creating request: {e}')
            raise

    def get_requests_for_user(self, user_id: str) -> List[AccessRequest]:
        expr = 'user_id = :user_id'
        attr_names = {}
        attr_values = {':user_id': user_id}
        return self._get_requests(expr, attr_names, attr_values)

    def get_requests_for_requester(self, requester_id: str) -> List[AccessRequest]:
        expr = 'requested_by = :requester_id'
        attr_names = {}
        attr_values = {':requester_id': requester_id}
        return self._get_requests(expr, attr_names, attr_values)

    def get_pending_requests(self) -> List[AccessRequest]:
        return self._get_requests_with_status(AccessRequestStatus.PENDING)

    def get_approved_requests(self) -> List[AccessRequest]:
        return self._get_requests_with_status(AccessRequestStatus.APPROVED)

    def _get_requests_with_status(self, status: AccessRequestStatus) -> List[AccessRequest]:
        expr = '#status = :status'
        attr_names = {'#status': 'status'}
        attr_values = {':status': status.value}
        return self._get_requests(expr, attr_names, attr_values)

    def _get_requests(self, expr, attr_names, attr_values) -> List[AccessRequest]:
        try:
            scan_args = {'FilterExpression': expr, 'ExpressionAttributeValues': attr_values}
            if attr_names:
                scan_args['ExpressionAttributeNames'] = attr_names
            response = self._table.scan(**scan_args)
            requests = [AccessRequest.from_dict(item) for item in response.get('Items', [])]
            logger.info(f'Retrieved {len(requests)} requests from DynamoDB')
            return requests
        except ClientError as e:
            logger.error(f'Error retrieving requests: {e}')
            raise

    def change_request_to_pending_approval(self, request_id: uuid.UUID) -> None:
        expr = 'SET #status = :status'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessRequestStatus.PENDING_APPROVAL.value,
        }
        self._update_request(request_id, expr, attr_names, attr_values)

    def approve_request(self, request_id: uuid.UUID, approved_by: str) -> None:
        expr = 'SET #status = :status, approved_by = :approved_by, approved_on = :approved_on'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessRequestStatus.APPROVED.value,
            ':approved_by': approved_by,
            ':approved_on': datetime.now(timezone.utc).isoformat(),
        }
        self._update_request(request_id, expr, attr_names, attr_values)

    def deny_request(self, request_id: uuid.UUID, approved_by: str) -> None:
        expr = 'SET #status = :status, approved_by = :approved_by, approved_on = :approved_on'
        attr_names = {
            '#status': 'status'}
        attr_values = {
            ':status': AccessRequestStatus.DENIED.value,
            ':approved_by': approved_by,
            ':approved_on': datetime.now(timezone.utc).isoformat(),
        }
        self._update_request(request_id, expr, attr_names, attr_values)

    def cancel_request(self, request_id: uuid.UUID) -> None:
        expr = 'SET #status = :status'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessRequestStatus.CANCELLED.value,
        }
        self._update_request(request_id, expr, attr_names, attr_values)

    def complete_request(self, request_id: uuid.UUID) -> None:
        expr = 'SET #status = :status'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessRequestStatus.COMPLETED.value,
        }
        self._update_request(request_id, expr, attr_names, attr_values)

    def _update_request(self, request_id, expr, attr_names, attr_values):
        try:
            self._table.update_item(
                Key={'id': str(request_id)},
                UpdateExpression=expr,
                ConditionExpression='attribute_exists(id)',
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values
            )
            logger.info(f'Updated request {request_id} to status {attr_values[':status']}')
        except ClientError as e:
            logger.error(f'Error updating request {request_id}: {e}')
            raise
