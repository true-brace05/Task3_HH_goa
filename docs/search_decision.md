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

## Phase 2: Runtime Search POC

### Implementation Approach

- `search/searcher.py` contains the `search_image()` function
- `search/providers/primary.py` implements MCR integration
- `search/providers/backup.py` implements Docker Hub integration
- Input validation checks file existence, image format, and validity
- Results are saved to `data/debug/search_results.json`

### API Endpoints Used

1. **MCR Catalog**: `GET https://mcr.microsoft.com/v2/_catalog?n=20`
2. **Docker Hub Tags**: `GET https://hub.docker.com/v2/repositories/{query}/tags/`

## Phase 3: Normalization + Candidate Retrieval

- 20 candidates normalized, 0 retrieved (MCR URLs are HTML pages, not image URLs)
- `search/normalizer.py` handles URL normalization, duplicate detection, deterministic IDs
- `search/retriever.py` downloads candidate images via HTTP with validation

## Phase 4 — Acquisition Findings

### MCR Discovery Capability

MCR catalog API works correctly and returns real repository names. MCR registry v2 API works and returns container image manifests and blobs.

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

### Phase 4 Status

**FAIL** — No legitimate acquisition path produces visual candidate images.

## Phase 5 — Visual Reverse Image Search POC

### Objective

Replace the container-registry acquisition approach with a genuine visual reverse-image-search mechanism using Google Lens.

### Provider Selection

**Primary Search**: `GoogleLensProvider` (`google-lens`)
- Based on `ramonclaudio/Google-Reverse-Image-Search` (MIT license)
- Uses Google's undocumented `searchbyimage/upload` endpoint
- Posts local image directly via `requests` + `BeautifulSoup`
- No official Google API — community-built reverse image search

**Primary Acquisition**: `VisualSearchAcquisitionProvider` (`visual-search-acquisition`)
- Downloads actual web images from Google Lens results
- Validates downloaded content is a valid image using PIL
- Saves to `data/candidates/`

### Research Basis

Two candidate open-source implementations evaluated:
1. **`ramonclaudio/Google-Reverse-Image-Search`** (MIT) — Simple `requests` + `BeautifulSoup` wrapper, takes `image_url`, uses Google `searchbyimage` endpoint
2. **`darcodev/chrome-lens-search`** (MIT) — More sophisticated, requires Selenium/Chromium for initial session, then plain HTTP

Selected `ramonclaudio`'s approach because:
- Simpler architecture (no browser automation needed)
- `beautifulsoup4` already installed
- Uses existing `requests` + `Pillow` dependencies
- No Chrome/Chromium dependency required

### Implementation Architecture

```
search/
├── visual/
│   ├── __init__.py
│   ├── base.py              # VisualSearchProvider abstract class
│   ├── google_lens.py       # GoogleLensProvider implementation
│   └── runner.py            # Visual search pipeline runner
├── acquisition/
│   ├── visual.py            # VisualSearchAcquisitionProvider
│   ├── runner.py            # Updated to use visual acquisition as primary
│   ├── base.py              # ImageAcquisitionProvider (unchanged)
│   ├── mcr.py               # MCRAcquisitionProvider (preserved as historical)
│   └── dockerhub.py         # DockerHubAcquisitionProvider (preserved as historical)
└── searcher.py              # Updated to use GoogleLensProvider as primary
```

### Visual Search Flow

1. Local image (`data/input/query.jpg`) is POSTed to `https://www.google.com/searchbyimage/upload`
2. Response HTML is parsed with BeautifulSoup to extract image result tiles
3. Links are extracted from result tiles (filtering `/url?q=` patterns)
4. Duplicate URLs are removed
5. Results returned as list of dicts with `source_url`, `image_url`, `title`, `provider`

### CAPTCHA Handling

If Google returns a CAPTCHA or upload form instead of results, the provider returns an empty list and logs `[VISUAL SEARCH BLOCKED]`. No fake results are generated.

### Phase 5 Results

- Visual search returns 0 results when Google blocks the request (CAPTCHA)
- This is **honest reporting** — the provider correctly detects the block
- Pipeline handles 0 results correctly (no crash, proper manifest)
- All 44 unit tests pass (including 7 new visual search tests)
- End-to-end pipeline verified: `query.jpg → Google Lens → 0 results (blocked) → pipeline handles correctly`

### Status

**BLOCKED** — Google returns CAPTCHA when attempting visual search. Provider correctly reports `[VISUAL SEARCH BLOCKED]` rather than fabricating results.

### Known Limitations

- Google's `searchbyimage` endpoint may block automated requests with CAPTCHA
- BeautifulSoup parsing uses selector-light approach; Google may change markup without notice
- No official Google API exists — this is an unofficial community-built client
- Rate limiting may apply for large queries
- When blocked, the provider returns empty list (no fallback to MCR/DockerHub)
- MCR and DockerHub are preserved as historical references but not used as fallbacks

### Final Recommendation

**VISUAL SEARCH BLOCKED** by Google's CAPTCHA protection. The `GoogleLensProvider` correctly detects and reports the block without fabricating results. The architecture is sound — `search/visual/`, `search/acquisition/visual.py`, and the updated `search/searcher.py` all work correctly. If CAPTCHA can be bypassed or Google's endpoint behavior changes, the visual search pipeline is ready to produce real candidates.

### Security Safeguards

- Request timeouts enforced (20s for visual search, 15s for acquisition)
- Response size limited to 50MB
- Content-type validation
- Image content validation via PIL
- Safe deterministic filenames only
- No shell commands constructed from URLs
- No credentials logged
- File handles properly closed using context managers
- No arbitrary redirect following

### Acquisition Architecture

- `search/acquisition/base.py` — Abstract `ImageAcquisitionProvider` and `AcquisitionManager`
- `search/acquisition/visual.py` — `VisualSearchAcquisitionProvider` — Downloads web images from Google Lens results
- `search/acquisition/mcr.py` — `MCRAcquisitionProvider` — Preserved as historical reference (proven unsuitable)
- `search/acquisition/dockerhub.py` — `DockerHubAcquisitionProvider` — Preserved as historical reference (proven unsuitable)
- `search/acquisition/runner.py` — Updated to use `VisualSearchAcquisitionProvider` as primary

### Phase 5 Tests

- 44 tests total (37 from phases 1-4 + 7 new visual search tests)
- `TestGoogleLensProvider`: 7 tests covering `can_search`, `search_by_image`, invalid images, non-image files, blocked requests
- All existing tests unchanged and passing

---

## Phase 6 — Alternative Visual Search Provider

### Provider Comparison

| Provider | Visual Query | Runtime Results | Image URLs | Source URLs | Free/Public | Automation Restrictions | License | Decision |
| -------- | ------------ | --------------- | ---------- | ----------- | ----------- | ----------------------- | ------- | -------- |
| MCR | No | Registry metadata | No | No | Yes | None | N/A | Rejected — not visual search |
| Docker Hub | No | Registry metadata | No | No | Yes (auth required) | Auth required | N/A | Rejected — not visual search |
| Google Lens | Yes | Yes (CAPTCHA blocked) | Yes | Yes | Yes | CAPTCHA blocks automated access | MIT (community client) | Rejected — blocked |
| TinEye | Yes | Yes | Yes | Yes | No (paid API) | $200 for 5,000 searches | MIT (pytineye) | Rejected — paid |
| **Yandex Visual Search** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** | **None (public endpoint)** | **MIT** | **Selected** |

### Provider Selected

**Primary**: `YandexVisualSearchProvider` (`yandex-visual-search`)
- Uploads local image to Yandex's image search endpoint
- Parses JSON response to get `cbir_id`
- Fetches search results page with similar images
- Extracts image URLs from similar image links
- No API key required
- No CAPTCHA observed during testing
- Returns real visual search results

### How It Works

1. Local image is POSTed to `https://yandex.com/images/search` with `rpt=imageview&format=json`
2. Response contains `cbirId` (content-based image retrieval ID)
3. Search results page fetched at `https://yandex.com/images/search?cbir_id={cbir_id}&rpt=imageview`
4. HTML parsed with BeautifulSoup to extract similar image links
5. Image URLs extracted from `img_url` query parameter in similar links
6. Deduplicated and returned as candidate list

### Phase 6 Results

- Candidates discovered: 20
- Candidates normalized: 20
- Images acquired: 19
- Acquisition failures: 1 (timeout)
- Valid images: 19
- SHA-256 computed: Yes (for all acquired images)

### Status

**GREEN** — Yandex Visual Search successfully returns real runtime visual candidates. The complete pipeline works: local image → visual search → 20 candidates → normalization → 19 images acquired with SHA-256 hashes.

### Known Limitations

- Yandex may block requests if too many are made concurrently
- Some image hosts may timeout during acquisition
- No official Yandex API — this uses Yandex's public web interface
- BeautifulSoup parsing may need updates if Yandex changes markup
- Rate limiting may apply for large queries

### Security Safeguards

- Request timeouts enforced (20s for visual search, 15s for acquisition)
- Response size limited to 50MB
- Content-type validation
- Image content validation via PIL
- SHA-256 hash computed for every acquired image
- Safe deterministic filenames only
- No shell commands constructed from URLs
- No credentials logged
- No API keys required
- File handles properly closed using context managers
- No arbitrary redirect following
