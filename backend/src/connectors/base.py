from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from src.models.document import DocumentRef, RawDocument


class Connector(ABC):
    platform: str

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    @abstractmethod
    def list_documents(self) -> list[DocumentRef]: ...

    @abstractmethod
    def fetch_document(self, ref: DocumentRef) -> RawDocument: ...


class APIConnector(ABC):
    """Base class for connectors that fetch data from remote APIs instead of local files."""

    platform: str

    @abstractmethod
    def list_documents(self) -> list[DocumentRef]: ...

    @abstractmethod
    def fetch_document(self, ref: DocumentRef) -> RawDocument: ...


class ConnectorRegistry:
    _connectors: dict[str, type[Connector]] = {}
    _api_connectors: dict[str, type[APIConnector]] = {}

    @classmethod
    def register(cls, platform: str, connector_class: type[Connector]) -> None:
        cls._connectors[platform] = connector_class

    @classmethod
    def register_api(cls, platform: str, connector_class: type[APIConnector]) -> None:
        cls._api_connectors[platform] = connector_class

    @classmethod
    def get(cls, platform: str) -> type[Connector] | type[APIConnector] | None:
        return cls._connectors.get(platform) or cls._api_connectors.get(platform)

    @classmethod
    def all_platforms(cls) -> list[str]:
        return list(cls._connectors.keys()) + list(cls._api_connectors.keys())

    @classmethod
    def create_all(cls, data_dir: str | Path) -> list[Connector]:
        data_path = Path(data_dir) / "sources"
        connectors = []
        for platform, connector_cls in cls._connectors.items():
            platform_dir = data_path / platform
            if platform_dir.exists():
                connectors.append(connector_cls(platform_dir))
        return connectors

    @classmethod
    def create_api(cls, platform: str) -> APIConnector | None:
        connector_cls = cls._api_connectors.get(platform)
        if connector_cls is None:
            return None
        return connector_cls()
