import uuid
import logging
from typing import List
from datetime import datetime, timezone
from botocore.exceptions import ClientError

from src.dynamo_db_utils import get_resource
from src.models import AccessGrant, AccessGrantStatus

logger = logging.getLogger(__name__)


class GrantRepository:

    def __init__(self):
        self._table = get_resource().Table('AccessGrant')

    def create_grant(self, grant: AccessGrant) -> None:
        try:
            self._table.put_item(Item=grant.to_dict())
            logger.info(f'Created new grant {grant.id}')
        except ClientError as e:
            logger.error(f'Error creating grant: {e}')
            raise

    def get_pending_grants(self) -> List[AccessGrant]:
        return self._get_grants_with_status(AccessGrantStatus.PENDING)

    def get_active_grants(self) -> List[AccessGrant]:
        return self._get_grants_with_status(AccessGrantStatus.ACTIVE)

    def get_expired_grants(self) -> List[AccessGrant]:
        now = datetime.now(timezone.utc)
        return [g for g in self.get_active_grants() if g.ends_on is not None and g.ends_on <= now]

    def _get_grants_with_status(self, status: AccessGrantStatus) -> List[AccessGrant]:
        expr = '#status = :status'
        attr_names = {'#status': 'status'}
        attr_values = {':status': status.value}
        return self._get_grants(expr, attr_names, attr_values)

    def _get_grants(self, expr, attr_names, attr_values) -> List[AccessGrant]:
        try:
            response = self._table.scan(
                FilterExpression=expr,
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values
            )
            grants = [AccessGrant.from_dict(item) for item in response.get('Items', [])]
            logger.info(f'Retrieved {len(grants)} grants from DynamoDB')
            return grants
        except ClientError as e:
            logger.error(f'Error retrieving grants: {e}')
            raise

    def activate_grant(self, grant_id: uuid.UUID) -> None:
        expr = 'SET #status = :status, granted_on = :granted_on'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessGrantStatus.ACTIVE.value,
            ':granted_on': datetime.now(timezone.utc).isoformat(),
        }
        self._update_grant(grant_id, expr, attr_names, attr_values)

    def revoke_grant(self, grant_id: uuid.UUID, revoked_by: str) -> None:
        expr = 'SET #status = :status, revoked_by = :revoked_by, revoked_on = :revoked_on'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessGrantStatus.REVOKED.value,
            ':revoked_by': revoked_by,
            ':revoked_on': datetime.now(timezone.utc).isoformat(),
        }
        self._update_grant(grant_id, expr, attr_names, attr_values)

    def set_grant_to_failed(self, grant_id: uuid.UUID) -> None:
        expr = 'SET #status = :status'
        attr_names = {'#status': 'status'}
        attr_values = {
            ':status': AccessGrantStatus.FAILED.value,
        }
        self._update_grant(grant_id, expr, attr_names, attr_values)

    def _update_grant(self, grant_id, expr, attr_names, attr_values):
        try:
            self._table.update_item(
                Key={'id': str(grant_id)},
                UpdateExpression=expr,
                ConditionExpression='attribute_exists(id)',
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values
            )
            logger.info(f'Updated grant {grant_id} to status {attr_values[':status']}')
        except ClientError as e:
            logger.error(f'Error updating grant {grant_id}: {e}')
            raise
