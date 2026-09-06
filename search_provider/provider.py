"""Runtime image search provider implementation."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RuntimeImage:
    name: str
    tag: str
    registry: str
    size_mb: int
    framework: str
    version: str
    description: str


@dataclass
class SearchResult:
    images: List[RuntimeImage]
    total_count: int
    query: str
    provider: str


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, **kwargs) -> SearchResult:
        pass

    @abstractmethod
    def get_image(self, name: str, tag: str) -> Optional[RuntimeImage]:
        pass


class RuntimeImageSearchProvider:
    def __init__(self, provider: Optional[SearchProvider] = None):
        self._provider = provider
        self._providers: dict[str, SearchProvider] = {}

    def register_provider(self, name: str, provider: SearchProvider):
        self._providers[name] = provider
        logger.info("Registered search provider: %s", name)

    def search(self, query: str, provider_name: Optional[str] = None, **kwargs) -> SearchResult:
        if provider_name and provider_name in self._providers:
            result = self._providers[provider_name].search(query, **kwargs)
            logger.info("Searched with provider '%s': %d results", provider_name, result.total_count)
            return result

        for name, provider in self._providers.items():
            try:
                result = provider.search(query, **kwargs)
                if result.total_count > 0:
                    logger.info("Found %d results from provider '%s'", result.total_count, name)
                    return result
            except Exception as e:
                logger.warning("Provider '%s' failed: %s", name, e)

        return SearchResult(images=[], total_count=0, query=query, provider="none")

    def get_image(self, name: str, tag: str = "latest") -> Optional[RuntimeImage]:
        for provider in self._providers.values():
            image = provider.get_image(name, tag)
            if image:
                return image
        return None

    @property
    def selected_provider(self) -> Optional[str]:
        return self._provider

    def select_provider(self, name: str):
        if name in self._providers:
            self._provider = self._providers[name]
            logger.info("Selected provider: %s", name)
        else:
            raise ValueError(f"Provider '{name}' not registered")
