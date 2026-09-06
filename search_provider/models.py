"""Data models for runtime image search."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Registry(Enum):
    DOCKER_HUB = "docker.io"
    AZURE_CONTAINER_REGISTRY = "azurecr.io"
    MICROSOFT_FOUNDRY = "mcr.microsoft.com"
    NVIDIA = "nvcr.io"
    HUGGING_FACE = "huggingface.co"


class Framework(Enum):
    PYTORCH = "pytorch"
    TENSORFLOW = "tensorflow"
    OPENAI = "openai"
    VLLM = "vllm"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class ImageStatus(Enum):
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    PREVIEW = "preview"
    UNAVAILABLE = "unavailable"


@dataclass
class RuntimeImage:
    name: str
    tag: str
    registry: str
    size_mb: int
    framework: str
    version: str
    status: ImageStatus = ImageStatus.AVAILABLE
    description: str = ""
    labels: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.registry}/{self.name}:{self.tag}"

    @property
    def is_available(self) -> bool:
        return self.status == ImageStatus.AVAILABLE


@dataclass
class SearchCriteria:
    query: str
    frameworks: List[str] = field(default_factory=list)
    min_size_mb: int = 0
    max_size_mb: int = 10000
    registry: Optional[str] = None
    status: Optional[ImageStatus] = None
    labels: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    images: List[RuntimeImage]
    total_count: int
    query: str
    provider: str
    facets: dict = field(default_factory=dict)

    @property
    def has_results(self) -> bool:
        return self.total_count > 0

    def __len__(self) -> int:
        return self.total_count
