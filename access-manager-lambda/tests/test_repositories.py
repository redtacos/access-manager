'''Repositories against an in-memory DynamoDB (moto).'''
from datetime import timedelta

import pytest

from src.models import (
    AccessGrantStatus, AccessRequestStatus, Notification, NotificationType,
)
from src.repositories import (
    GrantRepository, NotificationRepository, RequestRepository, TargetRepository,
)
from tests.factories import make_grant, make_request, make_target, utcnow
import uuid


@pytest.fixture
def requests_repo(dynamodb):
    return RequestRepository()


@pytest.fixture
def grants_repo(dynamodb):
    return GrantRepository()


@pytest.fixture
def targets_repo(dynamodb):
    return TargetRepository()


def stored(dynamodb, table, item_id):
    return dynamodb.Table(table).get_item(Key={'id': str(item_id)})['Item']


class TestRequestRepository:
    def test_a_created_request_can_be_read_back(self, requests_repo):
        request = make_request(starts_on=utcnow(), ends_on=utcnow() + timedelta(days=7))
        requests_repo.create_request(request)

        assert requests_repo.get_pending_requests() == [request]

    def test_pending_requests_only_contains_pending_ones(self, requests_repo):
        pending = make_request()
        requests_repo.create_request(pending)
        for status in AccessRequestStatus:
            if status != AccessRequestStatus.PENDING:
                requests_repo.create_request(make_request(status=status))

        assert requests_repo.get_pending_requests() == [pending]

    def test_approved_requests_only_contains_approved_ones(self, requests_repo):
        approved = make_request(status=AccessRequestStatus.APPROVED)
        requests_repo.create_request(approved)
        requests_repo.create_request(make_request(status=AccessRequestStatus.PENDING_APPROVAL))
        requests_repo.create_request(make_request(status=AccessRequestStatus.COMPLETED))

        assert requests_repo.get_approved_requests() == [approved]

    def test_no_requests_gives_an_empty_list(self, requests_repo):
        assert requests_repo.get_pending_requests() == []
        assert requests_repo.get_approved_requests() == []

    def test_changing_to_pending_approval(self, requests_repo, dynamodb):
        request = make_request()
        requests_repo.create_request(request)

        requests_repo.change_request_to_pending_approval(request.id)

        assert stored(dynamodb, 'AccessRequest', request.id)['status'] == 'pending_approval'

    def test_approving_records_who_and_when(self, requests_repo, dynamodb):
        request = make_request(status=AccessRequestStatus.PENDING_APPROVAL)
        requests_repo.create_request(request)

        requests_repo.approve_request(request.id, 'owner-1')

        item = stored(dynamodb, 'AccessRequest', request.id)
        assert item['status'] == 'approved'
        assert item['approved_by'] == 'owner-1'
        assert item['approved_on'] is not None

    def test_denying_records_who_and_when(self, requests_repo, dynamodb):
        request = make_request(status=AccessRequestStatus.PENDING_APPROVAL)
        requests_repo.create_request(request)

        requests_repo.deny_request(request.id, 'owner-1')

        item = stored(dynamodb, 'AccessRequest', request.id)
        assert item['status'] == 'denied'
        assert item['approved_by'] == 'owner-1'
        assert item['approved_on'] is not None

    def test_cancelling_and_completing(self, requests_repo, dynamodb):
        cancelled, completed = make_request(), make_request()
        requests_repo.create_request(cancelled)
        requests_repo.create_request(completed)

        requests_repo.cancel_request(cancelled.id)
        requests_repo.complete_request(completed.id)

        assert stored(dynamodb, 'AccessRequest', cancelled.id)['status'] == 'cancelled'
        assert stored(dynamodb, 'AccessRequest', completed.id)['status'] == 'completed'

    def test_a_status_change_leaves_the_other_fields_alone(self, requests_repo):
        request = make_request(reason='Needed for the audit')
        requests_repo.create_request(request)

        requests_repo.change_request_to_pending_approval(request.id)

        [updated] = requests_repo.get_requests_for_user(request.user_id)
        assert updated.reason == 'Needed for the audit'
        assert updated.user_id == request.user_id
        assert updated.target_id == request.target_id

    def test_requests_can_be_listed_per_user(self, requests_repo):
        mine = make_request(user_id='alice')
        requests_repo.create_request(mine)
        requests_repo.create_request(make_request(user_id='bob'))

        assert requests_repo.get_requests_for_user('alice') == [mine]

    def test_requests_can_be_listed_per_requester(self, requests_repo):
        on_behalf = make_request(user_id='alice', requested_by='owner-1')
        requests_repo.create_request(on_behalf)
        requests_repo.create_request(make_request(user_id='bob', requested_by='bob'))

        assert requests_repo.get_requests_for_requester('owner-1') == [on_behalf]


class TestGrantRepository:
    def test_a_created_grant_can_be_read_back(self, grants_repo):
        grant = make_grant(ends_on=utcnow() + timedelta(days=7))
        grants_repo.create_grant(grant)

        assert grants_repo.get_pending_grants() == [grant]

    def test_pending_and_active_grants_are_listed_separately(self, grants_repo):
        pending = make_grant(status=AccessGrantStatus.PENDING)
        active = make_grant(status=AccessGrantStatus.ACTIVE)
        for grant in (pending, active, make_grant(status=AccessGrantStatus.REVOKED),
                      make_grant(status=AccessGrantStatus.FAILED)):
            grants_repo.create_grant(grant)

        assert grants_repo.get_pending_grants() == [pending]
        assert grants_repo.get_active_grants() == [active]

    def test_no_grants_gives_an_empty_list(self, grants_repo):
        assert grants_repo.get_pending_grants() == []
        assert grants_repo.get_active_grants() == []
        assert grants_repo.get_expired_grants() == []

    def test_activating_records_when_the_access_was_granted(self, grants_repo, dynamodb):
        grant = make_grant()
        grants_repo.create_grant(grant)

        grants_repo.activate_grant(grant.id)

        item = stored(dynamodb, 'AccessGrant', grant.id)
        assert item['status'] == 'active'
        assert item['granted_on'] is not None

    def test_revoking_records_who_and_when(self, grants_repo, dynamodb):
        grant = make_grant(status=AccessGrantStatus.ACTIVE)
        grants_repo.create_grant(grant)

        grants_repo.revoke_grant(grant.id, 'system')

        item = stored(dynamodb, 'AccessGrant', grant.id)
        assert item['status'] == 'revoked'
        assert item['revoked_by'] == 'system'
        assert item['revoked_on'] is not None

    def test_a_grant_can_be_marked_as_failed(self, grants_repo, dynamodb):
        grant = make_grant()
        grants_repo.create_grant(grant)

        grants_repo.set_grant_to_failed(grant.id)

        assert stored(dynamodb, 'AccessGrant', grant.id)['status'] == 'failed'

    def test_only_active_grants_past_their_end_date_are_expired(self, grants_repo):
        now = utcnow()
        expired = make_grant(status=AccessGrantStatus.ACTIVE, ends_on=now - timedelta(minutes=1))
        for grant in (
            expired,
            make_grant(status=AccessGrantStatus.ACTIVE, ends_on=now + timedelta(days=1)),   # not yet
            make_grant(status=AccessGrantStatus.ACTIVE, ends_on=None),                      # indefinite
            make_grant(status=AccessGrantStatus.PENDING, ends_on=now - timedelta(days=1)),  # never granted
            make_grant(status=AccessGrantStatus.REVOKED, ends_on=now - timedelta(days=1)),  # already done
        ):
            grants_repo.create_grant(grant)

        assert grants_repo.get_expired_grants() == [expired]


class TestTargetRepository:
    def test_the_current_version_of_a_target_is_returned(self, targets_repo, dynamodb):
        target_id = uuid.uuid4()
        old = make_target(
            id=target_id, name='Old name',
            active_from=utcnow() - timedelta(days=60), active_to=utcnow() - timedelta(days=30),
        )
        current = make_target(id=target_id, name='Current name', active_from=utcnow() - timedelta(days=30))
        other = make_target(name='Another target')
        for target in (old, current, other):
            dynamodb.Table('AccessTarget').put_item(Item=target.to_dict())

        assert targets_repo.get_active_target_by_id(target_id) == current

    def test_an_unknown_target_is_an_error(self, targets_repo):
        with pytest.raises(LookupError):
            targets_repo.get_active_target_by_id(uuid.uuid4())

    def test_a_target_without_a_current_version_is_an_error(self, targets_repo, dynamodb):
        retired = make_target(active_to=utcnow() - timedelta(days=1))
        dynamodb.Table('AccessTarget').put_item(Item=retired.to_dict())

        with pytest.raises(LookupError):
            targets_repo.get_active_target_by_id(retired.id)


class TestNotificationRepository:
    def test_a_notification_is_stored(self, dynamodb):
        notification = Notification(
            id=uuid.uuid4(), request_id=uuid.uuid4(), user_id='owner-1',
            sent_on=utcnow(), type=NotificationType.APPROVAL_REQUEST,
        )

        NotificationRepository().create_notification(notification)

        item = stored(dynamodb, 'Notification', notification.id)
        assert item['user_id'] == 'owner-1'
        assert item['request_id'] == str(notification.request_id)
        assert item['type'] == 'approval_request'
