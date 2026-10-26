import uuid
from enum import Enum
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict

from .serialization import to_item, to_uuid, to_datetime, to_int


class AccessTargetApprovalMethod(Enum):
    AUTO = 'auto'
    OWNERS = 'owners'
    SPECIAL = 'special'


@dataclass
class AccessTarget:
    id: uuid.UUID
    active_from: datetime
    active_to: Optional[datetime]
    system: str
    name: str
    description: str
    owners: List[str]
    approval_method: AccessTargetApprovalMethod
    authorized_requesters: List[str]
    maximum_duration: int
    system_metadata: dict


    def to_dict(self):
        return to_item(asdict(self))

    @staticmethod
    def from_dict(data: dict) -> 'AccessTarget':
        data = data.copy()
        data['approval_method'] = AccessTargetApprovalMethod(data['approval_method'])
        data['id'] = to_uuid(data['id'])
        data['active_from'] = to_datetime(data['active_from'])
        data['active_to'] = to_datetime(data.get('active_to'))
        data['maximum_duration'] = to_int(data['maximum_duration'])
        return AccessTarget(**data)
