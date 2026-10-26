import uuid
import logging
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.models import AccessTarget
from src.dynamo_db_utils import get_resource

logger = logging.getLogger(__name__)


class TargetRepository:

    def __init__(self):
        self._table = get_resource().Table('AccessTarget')

    def get_active_target_by_id(self, id: uuid.UUID) -> AccessTarget:
        try:
            response = self._table.query(
                KeyConditionExpression=Key('id').eq(str(id)),
                ScanIndexForward=False,  # newest version first
            )
        except ClientError as e:
            logger.error(f'Error retrieving target: {e}')
            raise

        for item in response.get('Items', []):
            target = AccessTarget.from_dict(item)
            if target.active_to is None:
                return target
        raise LookupError(f'No active version of target {id}')
