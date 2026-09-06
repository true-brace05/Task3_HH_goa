"""Factory for creating and selecting runtime image search providers."""

import logging
from typing import Optional

from .models import RuntimeImage, SearchResult
from .provider import RuntimeImageSearchProvider, SearchProvider
from .providers import DockerHubProvider, AzureContainerRegistryProvider, MicrosoftFoundryProvider, MCRProvider

logger = logging.getLogger(__name__)


def create_default_provider() -> RuntimeImageSearchProvider:
    provider = RuntimeImageSearchProvider()
    provider.register_provider("dockerhub", DockerHubProvider())
    provider.register_provider("azurecr", AzureContainerRegistryProvider())
    provider.register_provider("microsoft-foundry", MicrosoftFoundryProvider())
    provider.register_provider("mcr", MCRProvider())
    provider.select_provider("microsoft-foundry")
    return provider


def create_provider(provider_type: str) -> RuntimeImageSearchProvider:
    runtime = RuntimeImageSearchProvider()

    if provider_type == "dockerhub":
        runtime.register_provider("dockerhub", DockerHubProvider())
    elif provider_type == "azurecr":
        runtime.register_provider("azurecr", AzureContainerRegistryProvider())
    elif provider_type == "microsoft-foundry":
        runtime.register_provider("microsoft-foundry", MicrosoftFoundryProvider())
    elif provider_type == "mcr":
        runtime.register_provider("mcr", MCRProvider())
    elif provider_type == "all":
        runtime.register_provider("dockerhub", DockerHubProvider())
        runtime.register_provider("azurecr", AzureContainerRegistryProvider())
        runtime.register_provider("microsoft-foundry", MicrosoftFoundryProvider())
        runtime.register_provider("mcr", MCRProvider())
    else:
        runtime.register_provider("dockerhub", DockerHubProvider())
        runtime.register_provider("microsoft-foundry", MicrosoftFoundryProvider())

    runtime.select_provider(provider_type if provider_type in ["dockerhub", "azurecr", "microsoft-foundry", "mcr"] else "microsoft-foundry")
    return runtime


def get_best_provider(query: str) -> str:
    if "openai" in query.lower() or "foundry" in query.lower():
        return "microsoft-foundry"
    if "azure" in query.lower():
        return "azurecr"
    if "nvidia" in query.lower():
        return "dockerhub"
    return "dockerhub"
