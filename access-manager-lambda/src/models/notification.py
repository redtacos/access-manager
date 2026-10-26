import uuid
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict

from .serialization import to_item, to_uuid, to_datetime


class NotificationType(Enum):
    APPROVAL_REQUEST = 'approval_request'
    REQUEST_COMPLETED = 'request_completed'
    ACCESS_GRANTED = 'access_granted'
    ACCESS_REVOKED = 'access_revoked'


@dataclass
class Notification:
    id: uuid.UUID
    request_id: uuid.UUID
    user_id: str
    sent_on: datetime
    type: NotificationType

    def to_dict(self):
        return to_item(asdict(self))

    @staticmethod
    def from_dict(data: dict) -> 'Notification':
        data = data.copy()
        data['type'] = NotificationType(data['type'])
        data['id'] = to_uuid(data['id'])
        data['request_id'] = to_uuid(data['request_id'])
        data['sent_on'] = to_datetime(data['sent_on'])
        return Notification(**data)
