# src/connectors/factory.py
from typing import Dict
from .base_connector import BaseConnector
from .okta_connector import OktaConnector


class ConnectorFactory:
    _connectors: Dict[str, BaseConnector] = {
        'Okta': OktaConnector(),
    }

    @classmethod
    def get_connector(cls, system_type: str) -> BaseConnector:
        if system_type not in cls._connectors:
            raise ValueError(f'Unsupported system type: {system_type}')

        return cls._connectors[system_type]
