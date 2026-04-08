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


class ConnectorRegistry:
    _connectors: dict[str, type[Connector]] = {}

    @classmethod
    def register(cls, platform: str, connector_class: type[Connector]) -> None:
        cls._connectors[platform] = connector_class

    @classmethod
    def get(cls, platform: str) -> type[Connector] | None:
        return cls._connectors.get(platform)

    @classmethod
    def all_platforms(cls) -> list[str]:
        return list(cls._connectors.keys())

    @classmethod
    def create_all(cls, data_dir: str | Path) -> list[Connector]:
        data_path = Path(data_dir) / "sources"
        connectors = []
        for platform, connector_cls in cls._connectors.items():
            platform_dir = data_path / platform
            if platform_dir.exists():
                connectors.append(connector_cls(platform_dir))
        return connectors
