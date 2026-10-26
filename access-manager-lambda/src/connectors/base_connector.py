from abc import ABC, abstractmethod
from src.models import AccessGrant, AccessTarget


class BaseConnector(ABC):
    @abstractmethod
    def provision_grant(self, grant: AccessGrant, target: AccessTarget) -> bool:
        pass

    @abstractmethod
    def deprovision_grant(self, grant: AccessGrant, target: AccessTarget) -> bool:
        pass

    @abstractmethod
    def validate_grant(self, grant: AccessGrant, target: AccessTarget) -> bool:
        pass
