'''OktaConnector against a fake Okta API.'''
import pytest
import requests
import responses

from src.connectors import BaseConnector, ConnectorFactory, OktaConnector
from tests.conftest import OKTA_TOKEN, OKTA_URL
from tests.factories import make_grant, make_target

GROUP, USER = 'grp-1', 'alice'
MEMBERSHIP = f'{OKTA_URL}/api/v1/groups/{GROUP}/users/{USER}'
USER_GROUPS = f'{OKTA_URL}/api/v1/users/{USER}/groups'


@pytest.fixture
def grant():
    return make_grant(user_id=USER)


@pytest.fixture
def target():
    return make_target(system_metadata={'group_id': GROUP})


@pytest.fixture
def connector(okta):
    return ConnectorFactory.get_connector('Okta')


class TestFactory:
    def test_okta_is_a_registered_system(self, connector):
        assert isinstance(connector, OktaConnector)
        assert isinstance(connector, BaseConnector)

    def test_unknown_systems_are_rejected(self):
        with pytest.raises(ValueError, match='Unsupported system type'):
            ConnectorFactory.get_connector('Mainframe')


class TestConfiguration:
    def test_the_token_can_come_from_the_environment(self, monkeypatch, okta, grant, target):
        monkeypatch.setenv('OKTA_API_TOKEN', 'from-env')
        connector = OktaConnector(base_url=OKTA_URL)
        okta.add(responses.PUT, MEMBERSHIP, status=204)

        connector.provision_grant(grant, target)

        assert 'from-env' in okta.calls[0].request.headers['Authorization']

    def test_the_base_url_can_come_from_the_environment(self, monkeypatch, okta, grant, target):
        monkeypatch.setenv('OKTA_BASE_URL', OKTA_URL)
        connector = OktaConnector(api_token=OKTA_TOKEN)
        okta.add(responses.PUT, MEMBERSHIP, status=204)

        assert connector.provision_grant(grant, target) is True


class TestProvisionGrant:
    def test_the_user_is_added_to_the_group(self, connector, okta, grant, target):
        okta.add(responses.PUT, MEMBERSHIP, status=204)

        assert connector.provision_grant(grant, target) is True

        assert len(okta.calls) == 1
        assert okta.calls[0].request.method == 'PUT'

    def test_the_request_is_authenticated(self, connector, okta, grant, target):
        okta.add(responses.PUT, MEMBERSHIP, status=204)

        connector.provision_grant(grant, target)

        assert OKTA_TOKEN in okta.calls[0].request.headers['Authorization']

    @pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500, 503])
    def test_an_error_response_is_a_failure(self, connector, okta, grant, target, status):
        okta.add(responses.PUT, MEMBERSHIP, status=status)

        assert connector.provision_grant(grant, target) is False

    def test_a_network_error_is_a_failure(self, connector, okta, grant, target):
        okta.add(responses.PUT, MEMBERSHIP, body=requests.exceptions.ConnectionError('down'))

        assert connector.provision_grant(grant, target) is False

    def test_a_timeout_is_a_failure(self, connector, okta, grant, target):
        okta.add(responses.PUT, MEMBERSHIP, body=requests.exceptions.Timeout('slow'))

        assert connector.provision_grant(grant, target) is False

    def test_a_target_without_a_group_id_is_a_failure_and_calls_nothing(self, connector, okta, grant):
        broken = make_target(system_metadata={})

        assert connector.provision_grant(grant, broken) is False
        assert len(okta.calls) == 0


class TestDeprovisionGrant:
    def test_the_user_is_removed_from_the_group(self, connector, okta, grant, target):
        okta.add(responses.DELETE, MEMBERSHIP, status=204)

        assert connector.deprovision_grant(grant, target) is True

        assert okta.calls[0].request.method == 'DELETE'
        assert OKTA_TOKEN in okta.calls[0].request.headers['Authorization']

    @pytest.mark.parametrize('status', [401, 404, 429, 500])
    def test_an_error_response_is_a_failure(self, connector, okta, grant, target, status):
        okta.add(responses.DELETE, MEMBERSHIP, status=status)

        assert connector.deprovision_grant(grant, target) is False

    def test_a_network_error_is_a_failure(self, connector, okta, grant, target):
        okta.add(responses.DELETE, MEMBERSHIP, body=requests.exceptions.ConnectionError('down'))

        assert connector.deprovision_grant(grant, target) is False

    def test_a_target_without_a_group_id_is_a_failure_and_calls_nothing(self, connector, okta, grant):
        assert connector.deprovision_grant(grant, make_target(system_metadata={})) is False
        assert len(okta.calls) == 0


class TestValidateGrant:
    def test_a_member_of_the_group_is_valid(self, connector, okta, grant, target):
        okta.add(responses.GET, USER_GROUPS, json=[{'id': 'other'}, {'id': GROUP}])

        assert connector.validate_grant(grant, target) is True

    def test_a_user_outside_the_group_is_not_valid(self, connector, okta, grant, target):
        okta.add(responses.GET, USER_GROUPS, json=[{'id': 'other'}])

        assert connector.validate_grant(grant, target) is False

    def test_an_error_is_not_valid(self, connector, okta, grant, target):
        okta.add(responses.GET, USER_GROUPS, status=500)

        assert connector.validate_grant(grant, target) is False
