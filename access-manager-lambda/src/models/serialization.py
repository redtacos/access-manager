import uuid
from enum import Enum
from datetime import datetime
from decimal import Decimal


def to_item(data: dict) -> dict:
    return {key: _storable(value) for key, value in data.items()}


def _storable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_uuid(value):
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def to_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def to_int(value):
    return int(value) if isinstance(value, Decimal) else value
