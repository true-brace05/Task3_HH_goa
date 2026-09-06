# Runtime Image Search Provider

A runtime image search provider for Microsoft Foundry that enables searching and selecting container images for AI agent deployments.

## Overview

This module provides a pluggable search provider system for discovering and selecting runtime container images across multiple registries including Docker Hub, Azure Container Registry, and Microsoft Foundry.

## Features

- **Multi-registry search**: Search across Docker Hub, Azure CR, Microsoft Foundry, and MCR
- **Pluggable providers**: Register custom search providers
- **Filtering**: Filter by framework, size, registry, and status
- **Provider selection**: Automatically select the best provider based on query context

## Quick Start

```python
from search_provider import create_default_provider

# Create provider with all registered backends
provider = create_default_provider()

# Search for runtime images
result = provider.search("openai runtime", frameworks=["openai"])
print(f"Found {result.total_count} images")

# Get a specific image
image = provider.get_image("openai/runtime", "latest")
print(f"Image: {image.full_name}")
```

## Provider Selection

The `get_best_provider` function selects the optimal provider based on query context:
- Queries containing "openai" or "foundry" → Microsoft Foundry
- Queries containing "azure" → Azure Container Registry
- Default → Docker Hub

## Configuration

See `config.json` for provider priorities, registry URLs, and default search criteria.

## License

MIT
