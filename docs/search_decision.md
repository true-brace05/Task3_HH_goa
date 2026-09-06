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

## Phase 4 — Acquisition Findings

### MCR Discovery Capability

MCR catalog API (`https://mcr.microsoft.com/v2/_catalog`) works correctly and returns real repository names. MCR registry v2 API (`/v2/{repo}/manifests/{tag}`, `/v2/{repo}/blobs/{digest}`) works and returns container image manifests and blobs.

### MCR Image Acquisition Capability

❌ **NOT CAPABLE OF VISUAL IMAGE ACQUISITION**

- MCR blobs return `application/octet-stream` with sizes ranging from 32 bytes to 543MB
- All blobs are container image layers (filesystem tar archives), not visual photographs
- MCR web pages contain no `<img>` tags or visual assets
- MCR serves container artifacts, not candidate photographs

### Docker Hub Acquisition Capability

❌ **NOT CAPABLE OF VISUAL IMAGE ACQUISITION**

- Docker Hub registry API requires authentication (HTTP 401)
- Even with authentication, Docker Hub serves container image layers
- Docker Hub web API returns repository tags, not direct image URLs
- No public endpoint provides visual candidate images without authentication

### Whether Docker Hub Was Useful as a Fallback

No. Docker Hub requires authentication for the registry API and also serves container artifacts. It cannot produce visual candidate images.

### Whether a Separate Acquisition Layer Is Required

Yes. The discovery and acquisition functions are fundamentally different:
- Discovery: finding repository metadata via catalog APIs
- Acquisition: obtaining visual image bytes from a source

The acquisition abstraction layer (`search/acquisition/`) was implemented to maintain this separation, but no legitimate provider currently produces visual candidate images.

### Final Recommendation

**IMAGE ACQUISITION BLOCKED.** No legitimate mechanism exists to acquire visual candidate images from the current providers. MCR and Docker Hub both serve container artifacts, not photographs. Face verification cannot proceed until a source of visual candidate images is identified.

### Final Recommendation

**IMAGE ACQUISITION BLOCKED.** No legitimate mechanism exists to acquire visual candidate images from MCR or Docker Hub. Both providers serve container artifacts, not photographs. Face verification cannot proceed until a source of visual candidate images is identified.

### Acquisition Architecture

- `search/acquisition/base.py` — Abstract `ImageAcquisitionProvider` and `AcquisitionManager`
- `search/acquisition/mcr.py` — `MCRAcquisitionProvider` — Tests MCR registry v2 API for blob access
- `search/acquisition/dockerhub.py` — `DockerHubAcquisitionProvider` — Tests Docker Hub registry
- `search/acquisition/runner.py` — Pipeline runner

### Phase 4 Results

- Candidates discovered: 20
- Candidates normalized: 20
- Acquisition attempted: 20
- Successfully acquired: 0
- Failed: 20

### Status

FAIL — No legitimate acquisition path produces visual candidate images.
