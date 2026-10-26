'''Shared fixtures.

* ``dynamodb``: an in-memory DynamoDB (moto) with the four tables created.
* ``okta``: a fake Okta API (``responses``) wired into the Okta connector.
* ``outbox``: replaces the notification channel (still a stub in the draft) so
  the tests can read what would have been sent.
'''
import pytest
import responses

try:  # moto >= 5
    from moto import mock_aws as mock_dynamodb
except ImportError:  # moto 4.x (the version pinned in requirements-dev.txt)
    from moto import mock_dynamodb

from src import dynamo_db_utils
from src.connectors import ConnectorFactory, OktaConnector
from src.services import NotificationService
from src.services import notification_service as notification_service_module

OKTA_URL = 'https://okta.test'
OKTA_TOKEN = 'test-token'


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    '''Fake credentials, so nothing can ever reach a real AWS account.'''
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    # dynamo_db_utils caches the resource in a module global: start clean.
    monkeypatch.setattr(dynamo_db_utils, '_resource', None)


@pytest.fixture
def dynamodb(aws_env):
    with mock_dynamodb():
        dynamo_db_utils._resource = None
        resource = dynamo_db_utils.get_resource()
        for name in ('AccessRequest', 'AccessGrant', 'Notification'):
            resource.create_table(
                TableName=name,
                KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST',
            )
        # Targets are versioned: keyed by id + active_from (see the README).
        resource.create_table(
            TableName='AccessTarget',
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'},
                {'AttributeName': 'active_from', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'active_from', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )
        yield resource
        dynamo_db_utils._resource = None


@pytest.fixture
def okta(monkeypatch):
    '''A fake Okta API. Register the calls you expect with ``okta.add(...)``.'''
    connector = OktaConnector(base_url=OKTA_URL, api_token=OKTA_TOKEN)
    monkeypatch.setitem(ConnectorFactory._connectors, 'Okta', connector)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


class Outbox:
    '''Captures notifications instead of sending them.'''

    def __init__(self):
        self.messages = []             # (recipient, message)
        self.approvers = ['owner-1']   # who the owners of any target are
        self.failing_recipients = set()

    def send(self, recipient, message):
        if recipient in self.failing_recipients:
            raise RuntimeError(f'channel down for {recipient}')
        self.messages.append((recipient, message))

    def to(self, recipient):
        return [message for who, message in self.messages if who == recipient]


@pytest.fixture
def outbox(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(
        NotificationService, '_send_notification',
        lambda self, recipient, message: box.send(recipient, message),
    )
    monkeypatch.setattr(
        NotificationService, '_find_approvers',
        lambda self, request: list(box.approvers),
    )
    return box


@pytest.fixture
def notification_service(monkeypatch, outbox):
    '''A NotificationService whose repository is a mock (no database needed).'''
    from unittest.mock import MagicMock
    monkeypatch.setattr(notification_service_module, 'NotificationRepository', MagicMock)
    return NotificationService()
