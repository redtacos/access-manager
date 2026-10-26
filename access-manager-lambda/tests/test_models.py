'''The models must survive a trip to and from DynamoDB.'''
from decimal import Decimal

import pytest

from src.models import (
    AccessGrant, AccessGrantStatus, AccessRequest, AccessRequestStatus,
    AccessTarget, AccessTargetApprovalMethod, Notification, NotificationType,
)
from tests.factories import make_grant, make_request, make_target, utcnow
import uuid


def assert_dynamodb_safe(value, path='item'):
    '''DynamoDB (boto3) cannot store UUIDs, datetimes or enums.'''
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            assert_dynamodb_safe(v, f'{path}[{i}]')
        return
    if isinstance(value, dict):
        for k, v in value.items():
            assert_dynamodb_safe(v, f'{path}.{k}')
        return
    pytest.fail(f'{path} is a {type(value).__name__}, which DynamoDB cannot store')


class TestAccessRequest:
    def test_round_trip(self):
        request = make_request(
            status=AccessRequestStatus.APPROVED,
            starts_on=utcnow(), ends_on=utcnow(),
            approved_by='owner-1', approved_on=utcnow(),
        )
        assert AccessRequest.from_dict(request.to_dict()) == request

    def test_to_dict_only_contains_storable_values(self):
        assert_dynamodb_safe(make_request(starts_on=utcnow()).to_dict())

    def test_status_is_stored_as_its_value(self):
        item = make_request(status=AccessRequestStatus.PENDING_APPROVAL).to_dict()
        assert item['status'] == 'pending_approval'

    def test_unknown_status_is_rejected(self):
        item = make_request().to_dict()
        item['status'] = 'nonsense'
        with pytest.raises(ValueError):
            AccessRequest.from_dict(item)

    def test_from_dict_does_not_mutate_its_input(self):
        item = make_request().to_dict()
        snapshot = dict(item)
        AccessRequest.from_dict(item)
        assert item == snapshot


class TestAccessGrant:
    def test_round_trip(self):
        grant = make_grant(
            status=AccessGrantStatus.REVOKED, granted_on=utcnow(),
            ends_on=utcnow(), revoked_on=utcnow(), revoked_by='system',
        )
        assert AccessGrant.from_dict(grant.to_dict()) == grant

    def test_to_dict_only_contains_storable_values(self):
        assert_dynamodb_safe(make_grant(granted_on=utcnow()).to_dict())

    def test_optional_fields_default_to_none(self):
        grant = AccessGrant(
            id=uuid.uuid4(), request_id=uuid.uuid4(), user_id='alice',
            target_id=uuid.uuid4(), status=AccessGrantStatus.PENDING,
        )
        assert grant.granted_on is None
        assert grant.ends_on is None
        assert grant.revoked_on is None
        assert grant.revoked_by is None


class TestAccessTarget:
    def test_round_trip(self):
        target = make_target(active_to=utcnow())
        assert AccessTarget.from_dict(target.to_dict()) == target

    def test_to_dict_only_contains_storable_values(self):
        assert_dynamodb_safe(make_target().to_dict())

    def test_approval_method_is_stored_as_its_value(self):
        item = make_target(approval_method=AccessTargetApprovalMethod.AUTO).to_dict()
        assert item['approval_method'] == 'auto'

    def test_numbers_read_back_from_dynamodb_become_ints(self):
        item = make_target(maximum_duration=30).to_dict()
        item['maximum_duration'] = Decimal('30')  # what boto3 returns
        assert AccessTarget.from_dict(item).maximum_duration == 30


class TestNotification:
    def test_round_trip(self):
        notification = Notification(
            id=uuid.uuid4(), request_id=uuid.uuid4(), user_id='owner-1',
            sent_on=utcnow(), type=NotificationType.APPROVAL_REQUEST,
        )
        assert Notification.from_dict(notification.to_dict()) == notification

    def test_to_dict_only_contains_storable_values(self):
        notification = Notification(
            id=uuid.uuid4(), request_id=uuid.uuid4(), user_id='owner-1',
            sent_on=utcnow(), type=NotificationType.APPROVAL_REQUEST,
        )
        item = notification.to_dict()
        assert_dynamodb_safe(item)
        assert item['type'] == 'approval_request'
