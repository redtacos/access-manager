'''Small builders for the domain objects used across the tests.'''
import uuid
from datetime import datetime, timedelta, timezone

from src.models import (
    AccessGrant,
    AccessGrantStatus,
    AccessRequest,
    AccessRequestStatus,
    AccessTarget,
    AccessTargetApprovalMethod,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_target(**overrides) -> AccessTarget:
    values = dict(
        id=uuid.uuid4(),
        active_from=utcnow() - timedelta(days=30),
        active_to=None,
        system='Okta',
        name='Engineering',
        description='Access to the engineering tools',
        owners=['owner-1'],
        approval_method=AccessTargetApprovalMethod.OWNERS,
        authorized_requesters=['everyone'],
        maximum_duration=30,
        system_metadata={'group_id': 'grp-1'},
    )
    values.update(overrides)
    return AccessTarget(**values)


def make_request(**overrides) -> AccessRequest:
    values = dict(
        id=uuid.uuid4(),
        user_id='alice',
        target_id=uuid.uuid4(),
        requested_by='alice',
        requested_on=utcnow(),
        reason='Needed for the project',
        status=AccessRequestStatus.PENDING,
        starts_on=None,
        ends_on=None,
        approved_by=None,
        approved_on=None,
    )
    values.update(overrides)
    return AccessRequest(**values)


def make_grant(**overrides) -> AccessGrant:
    values = dict(
        id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        user_id='alice',
        target_id=uuid.uuid4(),
        status=AccessGrantStatus.PENDING,
        granted_on=None,
        ends_on=None,
        revoked_on=None,
        revoked_by=None,
    )
    values.update(overrides)
    return AccessGrant(**values)
