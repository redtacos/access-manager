import uuid
from enum import Enum
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, asdict

from .serialization import to_item, to_uuid, to_datetime


class AccessGrantStatus(Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    REVOKED = 'revoked'
    FAILED = 'failed'


@dataclass
class AccessGrant:
    id: uuid.UUID
    request_id: uuid.UUID
    user_id: str
    target_id: uuid.UUID
    status: AccessGrantStatus
    granted_on: Optional[datetime] = None
    ends_on: Optional[datetime] = None
    revoked_on: Optional[datetime] = None
    revoked_by: Optional[str] = None

    def to_dict(self):
        return to_item(asdict(self))

    @staticmethod
    def from_dict(data: dict) -> 'AccessGrant':
        data = data.copy()
        data['status'] = AccessGrantStatus(data['status'])
        for field in ('id', 'request_id', 'target_id'):
            data[field] = to_uuid(data[field])
        for field in ('granted_on', 'ends_on', 'revoked_on'):
            data[field] = to_datetime(data.get(field))
        return AccessGrant(**data)
