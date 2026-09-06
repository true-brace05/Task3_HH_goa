"""Docker Hub runtime image search provider."""

import logging
from typing import List, Optional

from .models import RuntimeImage, SearchCriteria, SearchResult, Registry, Framework, ImageStatus
from .provider import SearchProvider

logger = logging.getLogger(__name__)


class DockerHubProvider(SearchProvider):
    def __init__(self):
        self._registry = Registry.DOCKER_HUB.value
        self._name = "dockerhub"

    def search(self, query: str, **kwargs) -> SearchResult:
        logger.info("Searching Docker Hub for: %s", query)
        images = self._build_results(query, kwargs)
        return SearchResult(
            images=images,
            total_count=len(images),
            query=query,
            provider=self._name
        )

    def get_image(self, name: str, tag: str = "latest") -> Optional[RuntimeImage]:
        logger.info("Fetching image: %s:%s from %s", name, tag, self._registry)
        return RuntimeImage(
            name=name,
            tag=tag,
            registry=self._registry,
            size_mb=0,
            framework=Framework.CUSTOM.value,
            version=tag,
            description=f"{name}:{tag} from Docker Hub"
        )

    def _build_results(self, query: str, kwargs: dict) -> List[RuntimeImage]:
        frameworks = kwargs.get("frameworks", [])
        images = []
        for fw in frameworks or [Framework.CUSTOM.value]:
            images.append(RuntimeImage(
                name=query,
                tag="latest",
                registry=self._registry,
                size_mb=1024,
                framework=fw,
                version="1.0",
                description=f"{query} runtime image"
            ))
        return images


class AzureContainerRegistryProvider(SearchProvider):
    def __init__(self):
        self._registry = Registry.AZURE_CONTAINER_REGISTRY.value
        self._name = "azurecr"

    def search(self, query: str, **kwargs) -> SearchResult:
        logger.info("Searching Azure Container Registry for: %s", query)
        images = self._build_results(query, kwargs)
        return SearchResult(
            images=images,
            total_count=len(images),
            query=query,
            provider=self._name
        )

    def get_image(self, name: str, tag: str = "latest") -> Optional[RuntimeImage]:
        return RuntimeImage(
            name=name,
            tag=tag,
            registry=self._registry,
            size_mb=2048,
            framework=Framework.CUSTOM.value,
            version=tag,
            description=f"{name}:{tag} from Azure Container Registry"
        )

    def _build_results(self, query: str, kwargs: dict) -> List[RuntimeImage]:
        return [RuntimeImage(
            name=query,
            tag="latest",
            registry=self._registry,
            size_mb=2048,
            framework=Framework.CUSTOM.value,
            version="1.0",
            description=f"{query} runtime from ACR"
        )]


class MicrosoftFoundryProvider(SearchProvider):
    def __init__(self):
        self._registry = Registry.MICROSOFT_FOUNDRY.value
        self._name = "microsoft-foundry"

    def search(self, query: str, **kwargs) -> SearchResult:
        logger.info("Searching Microsoft Foundry for: %s", query)
        images = self._build_results(query, kwargs)
        return SearchResult(
            images=images,
            total_count=len(images),
            query=query,
            provider=self._name
        )

    def get_image(self, name: str, tag: str = "latest") -> Optional[RuntimeImage]:
        return RuntimeImage(
            name=name,
            tag=tag,
            registry=self._registry,
            size_mb=3072,
            framework=Framework.OPENAI.value,
            version=tag,
            description=f"{name}:{tag} from Microsoft Foundry"
        )

    def _build_results(self, query: str, kwargs: dict) -> List[RuntimeImage]:
        return [RuntimeImage(
            name=query,
            tag="latest",
            registry=self._registry,
            size_mb=3072,
            framework=Framework.OPENAI.value,
            version="1.0",
            status=ImageStatus.AVAILABLE,
            description=f"{query} Foundry runtime image"
        )]


class MCRProvider(SearchProvider):
    def __init__(self):
        self._registry = Registry.MICROSOFT_FOUNDRY.value
        self._name = "mcr"

    def search(self, query: str, **kwargs) -> SearchResult:
        logger.info("Searching MCR for: %s", query)
        images = self._build_results(query, kwargs)
        return SearchResult(
            images=images,
            total_count=len(images),
            query=query,
            provider=self._name
        )

    def get_image(self, name: str, tag: str = "latest") -> Optional[RuntimeImage]:
        return RuntimeImage(
            name=name,
            tag=tag,
            registry=self._registry,
            size_mb=2560,
            framework=Framework.CUSTOM.value,
            version=tag,
            description=f"{name}:{tag} from MCR"
        )

    def _build_results(self, query: str, kwargs: dict) -> List[RuntimeImage]:
        return [RuntimeImage(
            name=query,
            tag="latest",
            registry=self._registry,
            size_mb=2560,
            framework=Framework.CUSTOM.value,
            version="1.0",
            description=f"{query} MCR runtime image"
        )]
