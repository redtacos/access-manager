'''End-to-end tests: the whole Lambda against an in-memory DynamoDB and a fake Okta.

Nothing is mocked inside the application. The only fakes are the edges:

* DynamoDB          -> moto
* the Okta API      -> ``responses`` (the real OktaConnector makes real HTTP calls
                       that are intercepted)
* the notification  -> the ``outbox`` fixture (the channel is still a stub)

The approval itself is an API call that does not exist yet, so the tests do what
the API would do: record the decision with ``RequestRepository.approve_request``.
'''
from datetime import timedelta
from types import SimpleNamespace

import pytest
import responses

from src.lambda_function import lambda_handler
from src.models import (
    AccessGrant, AccessGrantStatus, AccessRequest, AccessRequestStatus,
    AccessTargetApprovalMethod,
)
from src.repositories import GrantRepository, RequestRepository
from src.services import NotificationService
from tests.conftest import OKTA_URL
from tests.factories import make_request, make_target, utcnow

CONTEXT = SimpleNamespace(function_name='access-manager', aws_request_id='e2e')


def membership_url(group='grp-1', user='alice'):
    return f'{OKTA_URL}/api/v1/groups/{group}/users/{user}'


class World:
    '''The environment of one scenario, with a few helpers to set it up and look at it.'''

    def __init__(self, dynamodb, okta, outbox):
        self.db, self.okta, self.outbox = dynamodb, okta, outbox
        self.requests, self.grants = RequestRepository(), GrantRepository()
        self.iam_team = NotificationService()._iam_team_recipient

    # -- setting up
    def add_target(self, **overrides):
        target = make_target(**overrides)
        self.db.Table('AccessTarget').put_item(Item=target.to_dict())
        return target

    def add_request(self, target, **overrides):
        values = dict(target_id=target.id, ends_on=utcnow() + timedelta(days=7))
        values.update(overrides)
        request = make_request(**values)
        self.requests.create_request(request)
        return request

    def expire(self, grant):
        '''Moves the end date of a grant into the past.'''
        self.db.Table('AccessGrant').update_item(
            Key={'id': str(grant.id)},
            UpdateExpression='SET ends_on = :ends_on',
            ExpressionAttributeValues={':ends_on': (utcnow() - timedelta(minutes=1)).isoformat()},
        )

    # -- running
    def run(self):
        response = lambda_handler({}, CONTEXT)
        assert response['statusCode'] == 200, response
        return response

    # -- looking at the result
    def request(self, request) -> AccessRequest:
        item = self.db.Table('AccessRequest').get_item(Key={'id': str(request.id)})['Item']
        return AccessRequest.from_dict(item)

    def grants_of(self, request) -> list:
        items = self.db.Table('AccessGrant').scan()['Items']
        return [AccessGrant.from_dict(i) for i in items if i['request_id'] == str(request.id)]

    def okta_calls(self, method):
        return [c for c in self.okta.calls if c.request.method == method]


@pytest.fixture
def world(dynamodb, okta, outbox):
    return World(dynamodb, okta, outbox)


def test_an_owner_approved_request_goes_from_request_to_revocation(world):
    '''The whole life of an access: request, approval, provisioning, expiry, revocation.'''
    world.okta.add(responses.PUT, membership_url(), status=204)
    world.okta.add(responses.DELETE, membership_url(), status=204)
    target = world.add_target(approval_method=AccessTargetApprovalMethod.OWNERS)
    request = world.add_request(target, user_id='alice')

    # Run 1: the request needs an approval, so the owner is asked. Nothing happens in Okta yet.
    world.run()

    assert world.request(request).status == AccessRequestStatus.PENDING_APPROVAL
    assert len(world.outbox.to('owner-1')) == 1
    assert 'alice' in world.outbox.to('owner-1')[0]
    assert world.grants_of(request) == []
    assert len(world.okta.calls) == 0

    # The owner approves (through the API, which is not built yet).
    world.requests.approve_request(request.id, 'owner-1')

    # Run 2: the grant is created, the request completed, alice added to the Okta group.
    world.run()

    completed = world.request(request)
    assert completed.status == AccessRequestStatus.COMPLETED
    assert completed.approved_by == 'owner-1'
    [grant] = world.grants_of(request)
    assert grant.status == AccessGrantStatus.ACTIVE
    assert grant.user_id == 'alice'
    assert grant.target_id == target.id
    assert grant.granted_on is not None
    assert len(world.okta_calls('PUT')) == 1
    assert len(world.outbox.to('alice')) == 1          # one message for both events
    assert 'approved' in world.outbox.to('alice')[0].lower()
    assert 'granted' in world.outbox.to('alice')[0].lower()
    assert world.outbox.to(world.iam_team) == []

    # Run 3: nothing changed, so nothing happens (the run is idempotent).
    messages_before = list(world.outbox.messages)
    world.run()

    assert len(world.grants_of(request)) == 1
    assert len(world.okta.calls) == 1
    assert world.outbox.messages == messages_before

    # The end date is reached.
    world.expire(grant)

    # Run 4: alice is removed from the Okta group and the grant is revoked.
    world.run()

    [revoked] = world.grants_of(request)
    assert revoked.status == AccessGrantStatus.REVOKED
    assert revoked.revoked_by.lower() == 'system'
    assert revoked.revoked_on is not None
    assert len(world.okta_calls('DELETE')) == 1
    assert 'revoked' in world.outbox.to('alice')[-1].lower()

    # Run 5: still idempotent.
    world.run()

    assert len(world.okta_calls('DELETE')) == 1
    assert len(world.okta_calls('PUT')) == 1


def test_an_auto_approved_request_is_provisioned_in_a_single_run(world):
    world.okta.add(responses.PUT, membership_url(), status=204)
    target = world.add_target(approval_method=AccessTargetApprovalMethod.AUTO)
    request = world.add_request(target, user_id='alice')

    world.run()

    stored = world.request(request)
    assert stored.status == AccessRequestStatus.COMPLETED
    assert stored.approved_by.lower() == 'system'
    [grant] = world.grants_of(request)
    assert grant.status == AccessGrantStatus.ACTIVE
    assert len(world.okta_calls('PUT')) == 1
    assert world.outbox.to('owner-1') == []             # nobody had to approve
    assert len(world.outbox.to('alice')) == 1


def test_an_okta_outage_is_reported_and_recovered_on_the_next_run(world):
    world.okta.add(responses.PUT, membership_url(), status=500)
    target = world.add_target(approval_method=AccessTargetApprovalMethod.AUTO)
    request = world.add_request(target, user_id='alice')

    # Run 1: Okta is down. The grant exists but is not active, and the IAM team is told once.
    world.run()

    completed = world.request(request)
    assert completed.status == AccessRequestStatus.COMPLETED
    [grant] = world.grants_of(request)
    assert grant.status == AccessGrantStatus.PENDING
    [report] = world.outbox.to(world.iam_team)
    assert str(grant.id) in report
    assert all('granted' not in message.lower() for message in world.outbox.to('alice'))

    # Run 2: Okta is back. The same grant is retried and succeeds.
    world.okta.replace(responses.PUT, membership_url(), status=204)
    world.run()

    [grant] = world.grants_of(request)
    assert grant.status == AccessGrantStatus.ACTIVE
    assert len(world.okta_calls('PUT')) == 2
    assert any('granted' in message.lower() for message in world.outbox.to('alice'))
    assert len(world.outbox.to(world.iam_team)) == 1    # no second error report


def test_one_failing_request_does_not_block_the_others(world):
    world.okta.add(responses.PUT, membership_url(user='bob'), status=204)
    unsupported = world.add_target(approval_method=AccessTargetApprovalMethod.AUTO, system='Mainframe')
    supported = world.add_target(approval_method=AccessTargetApprovalMethod.AUTO)
    broken = world.add_request(unsupported, user_id='alice')
    healthy = world.add_request(supported, user_id='bob')

    world.run()

    [good_grant] = world.grants_of(healthy)
    assert good_grant.status == AccessGrantStatus.ACTIVE
    [bad_grant] = world.grants_of(broken)
    assert bad_grant.status == AccessGrantStatus.PENDING
    [report] = world.outbox.to(world.iam_team)
    assert 'Unsupported system type' in report


def test_a_request_for_a_missing_target_is_reported_and_changes_nothing(world):
    request = world.add_request(make_target())   # the target is never saved

    world.run()

    assert world.request(request).status == AccessRequestStatus.PENDING
    assert world.grants_of(request) == []
    assert len(world.outbox.to(world.iam_team)) == 1


def test_special_process_requests_are_not_auto_approved(world):
    target = world.add_target(approval_method=AccessTargetApprovalMethod.SPECIAL)
    request = world.add_request(target)

    world.run()

    assert world.request(request).status not in (
        AccessRequestStatus.APPROVED, AccessRequestStatus.COMPLETED
    )
    assert world.grants_of(request) == []
    assert len(world.okta.calls) == 0
    assert len(world.outbox.to(world.iam_team)) == 1


def test_an_indefinite_access_is_never_expired(world):
    world.okta.add(responses.PUT, membership_url(), status=204)
    target = world.add_target(approval_method=AccessTargetApprovalMethod.AUTO)
    request = world.add_request(target, ends_on=None)

    world.run()
    world.run()

    [grant] = world.grants_of(request)
    assert grant.status == AccessGrantStatus.ACTIVE
    assert world.okta_calls('DELETE') == []


@pytest.mark.xfail(
    reason='TODO in the code: create the grant and complete the request in one transaction',
    strict=False,
)
def test_a_failure_while_completing_a_request_does_not_lead_to_a_second_grant(world, monkeypatch):
    world.okta.add(responses.PUT, membership_url(), status=204)
    target = world.add_target(approval_method=AccessTargetApprovalMethod.AUTO)
    request = world.add_request(target, status=AccessRequestStatus.APPROVED, approved_by='system')

    real_complete = RequestRepository.complete_request
    attempts = {'count': 0}

    def flaky_complete(self, request_id):
        attempts['count'] += 1
        if attempts['count'] == 1:
            raise RuntimeError('write failed')
        return real_complete(self, request_id)

    monkeypatch.setattr(RequestRepository, 'complete_request', flaky_complete)

    world.run()
    world.run()

    assert len(world.grants_of(request)) == 1
