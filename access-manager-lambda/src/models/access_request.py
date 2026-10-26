import uuid
from enum import Enum
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, asdict

from .serialization import to_item, to_uuid, to_datetime


class AccessRequestStatus(Enum):
    PENDING = 'pending'
    PENDING_APPROVAL = 'pending_approval'
    APPROVED = 'approved'
    DENIED = 'denied'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'


@dataclass
class AccessRequest:
    id: uuid.UUID
    user_id: str
    target_id: uuid.UUID
    requested_by: str
    requested_on: datetime
    reason: str
    status: AccessRequestStatus
    starts_on: Optional[datetime] = None
    ends_on: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_on: Optional[datetime] = None

    def to_dict(self):
        return to_item(asdict(self))

    @staticmethod
    def from_dict(data: dict) -> 'AccessRequest':
        data = data.copy()
        data['status'] = AccessRequestStatus(data['status'])
        data['id'] = to_uuid(data['id'])
        data['target_id'] = to_uuid(data['target_id'])
        for field in ('requested_on', 'starts_on', 'ends_on', 'approved_on'):
            data[field] = to_datetime(data.get(field))
        return AccessRequest(**data)
