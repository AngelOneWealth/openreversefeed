"""Adapter registry with priority-based detection. See spec §6.1."""
from __future__ import annotations

from openreversefeed.adapters.base import FeedAdapter


class UnknownFormatError(Exception):
    def __init__(self, headers: set[str]) -> None:
        self.headers = sorted(headers)
        super().__init__(
            f"no registered FeedAdapter matches headers: {self.headers}"
        )


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[type[FeedAdapter]] = []

    def register(self, adapter_cls: type[FeedAdapter]) -> type[FeedAdapter]:
        self._adapters.append(adapter_cls)
        return adapter_cls

    def detect(self, headers: set[str]) -> FeedAdapter:
        candidates = [
            cls
            for cls in self._adapters
            if cls.mandatory_headers.issubset(headers)
            and (not cls.discriminator_headers or (cls.discriminator_headers & headers))
        ]
        if not candidates:
            raise UnknownFormatError(headers)
        candidates.sort(key=lambda cls: (-cls.priority, cls.name))
        return candidates[0]()


default_registry = AdapterRegistry()
