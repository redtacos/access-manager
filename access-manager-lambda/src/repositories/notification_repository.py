import logging
from botocore.exceptions import ClientError

from src.models import Notification
from src.dynamo_db_utils import get_resource

logger = logging.getLogger(__name__)


class NotificationRepository:

    def __init__(self):
        self._table = get_resource().Table('Notification')

    def create_notification(self, notification: Notification) -> None:
        try:
            self._table.put_item(Item=notification.to_dict())
            logger.info(f'Registered a new notification {notification.id}')
        except ClientError as e:
            logger.error(f'Error creating notification: {e}')
            raise
