# Search Decision Document

## Phase 1: Provider Selection

### Decision

The **Microsoft Foundry (MCR)** provider was selected as the PRIMARY runtime image search provider.

### Rationale

1. **MCR (`mcr.microsoft.com`)** is the official Microsoft Container Registry for Azure and Foundry runtime images
2. Provides public catalog access without authentication
3. Returns real repository data via the v2 registry API
4. Directly relevant to the Microsoft Foundry ecosystem

### Backup Provider

**Docker Hub** (`docker.io`) was selected as the BACKUP provider:
- Largest public container image repository
- Stable v2 API for repository tags
- Fallback when MCR is unavailable

### Provider Configuration

```json
{
  "primary": "microsoft-foundry",
  "backup": "dockerhub",
  "mcr_catalog": "https://mcr.microsoft.com/v2/_catalog",
  "dockerhub_api": "https://hub.docker.com/v2/repositories/{query}/tags/"
}
```

## Phase 2: Runtime Search POC

### Implementation Approach

- `search/searcher.py` contains the `search_image()` function
- `search/providers/primary.py` implements MCR integration
- `search/providers/backup.py` implements Docker Hub integration
- Input validation checks file existence, image format, and validity
- Results are saved to `data/debug/search_results.json`

### API Endpoints Used

1. **MCR Catalog**: `GET https://mcr.microsoft.com/v2/_catalog?n=20`
   - Returns real repository names from Microsoft Container Registry
   
2. **Docker Hub Tags**: `GET https://hub.docker.com/v2/repositories/{query}/tags/`
   - Returns real tags for public repositories

### Why Not Mocks

The Phase 2 prompt explicitly requires:
- Real runtime search results
- No hardcoded candidate results
- No manually inserted URLs
- No fake/mock results

Therefore, the implementation queries actual MCR and Docker Hub APIs.
