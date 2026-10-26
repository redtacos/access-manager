import os
import logging
import requests
from typing import Optional

from src.models import AccessGrant, AccessTarget
from .base_connector import BaseConnector

logger = logging.getLogger(__name__)


class OktaConnector(BaseConnector):
    def __init__(self, base_url: Optional[str] = None, api_token: Optional[str] = None):
        self.base_url = (base_url or os.getenv('OKTA_BASE_URL', '')).rstrip('/')
        self.api_token = api_token or os.getenv('OKTA_API_TOKEN', '')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

    def provision_grant(self, grant: AccessGrant, target: AccessTarget) -> bool:
        try:
            group_id = self._group_id(target)
            response = self.session.put(self._membership_url(group_id, grant.user_id), timeout=10)
            response.raise_for_status()
            logger.info(f'Successfully added user {grant.user_id} to group {group_id}')
            return True
        except Exception as e:
            logger.error(f'Failed to add user {grant.user_id} to Okta group: {e}')
            return False

    def deprovision_grant(self, grant: AccessGrant, target: AccessTarget) -> bool:
        try:
            group_id = self._group_id(target)
            response = self.session.delete(self._membership_url(group_id, grant.user_id), timeout=10)
            response.raise_for_status()
            logger.info(f'Successfully removed user {grant.user_id} from group {group_id}')
            return True
        except Exception as e:
            logger.error(f'Failed to remove user {grant.user_id} from Okta group: {e}')
            return False

    def validate_grant(self, grant: AccessGrant, target: AccessTarget) -> bool:
        try:
            group_id = self._group_id(target)
            response = self.session.get(f'{self.base_url}/api/v1/users/{grant.user_id}/groups', timeout=10)
            response.raise_for_status()
            return group_id in [group['id'] for group in response.json()]
        except Exception as e:
            logger.error(f'Error verifying Okta membership of user {grant.user_id}: {e}')
            return False

    def _membership_url(self, group_id: str, user_id: str) -> str:
        return f'{self.base_url}/api/v1/groups/{group_id}/users/{user_id}'

    @staticmethod
    def _group_id(target: AccessTarget) -> str:
        group_id = (target.system_metadata or {}).get('group_id')
        if not group_id:
            raise ValueError(f'Target {target.id} has no Okta group_id in its system metadata')
        return group_id
