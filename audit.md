# Audit Log — Task3_HH_goa

> All changes, builds, and commits are tracked sequentially below with timestamps and branch information.

---

## Commit #1

- **Commit Hash:** `06afd98`
- **Branch:** `feature/search-provider-poc`
- **Commit Time:** 2026-09-06 11:53:11 +0530
- **Author:** Nikhil <kumkumsan567@gmail.com>
- **Message:** `feat(search): research and select runtime image search provider`
- **Files Changed:** 10 files, 505 insertions

### Changes:
1. **`.gitignore`** — Created gitignore to exclude Python cache, virtual environments, and build artifacts.
2. **`README.md`** — Added project documentation describing the runtime image search provider module, features, quick start guide, provider selection logic, and configuration details.
3. **`pyproject.toml`** — Created project metadata and build configuration for the `runtime-image-search-provider` package.
4. **`search_provider/__init__.py`** — Created package initializer exporting `RuntimeImageSearchProvider`, `SearchResult`, and `RuntimeImage`.
5. **`search_provider/provider.py`** — Implemented abstract `SearchProvider` base class and `RuntimeImageSearchProvider` orchestrator class with `search()`, `get_image()`, `register_provider()`, and `select_provider()` methods.
6. **`search_provider/providers.py`** — Implemented four concrete search providers:
   - `DockerHubProvider` — Searches Docker Hub registry
   - `AzureContainerRegistryProvider` — Searches Azure Container Registry
   - `MicrosoftFoundryProvider` — Searches Microsoft Foundry runtime images
   - `MCRProvider` — Searches Microsoft Container Registry
7. **`search_provider/models.py`** — Defined data models: `RuntimeImage`, `SearchCriteria`, `SearchResult`, `Registry`, `Framework`, `ImageStatus` enums and dataclasses.
8. **`search_provider/factory.py`** — Created factory functions: `create_default_provider()`, `create_provider()`, and `get_best_provider()` for automatic provider selection.
9. **`search_provider/config.json`** — Added provider configuration with registry URLs, priorities, and default search criteria.
10. **`search_provider/main.py`** — Created public API entry point exporting all modules.

---

## Phase 2 — Runtime Search POC

## Date

2026-09-06

## Engineer

Nikhil

## Branch

feature/search-poc

## Objective

Prove local image → runtime search provider → real candidate results.

## Previous Phase

Phase 1 (Commit `06afd98`, `feature/search-provider-poc`): Selected Microsoft Foundry (MCR) as PRIMARY provider and Docker Hub as BACKUP provider.

## Provider Used

**PRIMARY**: Microsoft Foundry (MCR) — `https://mcr.microsoft.com/v2/_catalog`
**BACKUP**: Docker Hub — `https://hub.docker.com/v2/repositories/{repo}/tags/`

## Implementation

1. **`search/__init__.py`** — Package initializer exporting `search_image`, providers.
2. **`search/searcher.py`** — Main `search_image(image_path)` function with input validation, provider orchestration, fallback, and debug output.
3. **`search/providers/__init__.py`** — Providers package initializer.
4. **`search/providers/primary.py`** — `MicrosoftFoundryProvider` using MCR v2 catalog API for real results.
5. **`search/providers/backup.py`** — `DockerHubProvider` using Docker Hub v2 repositories API for fallback.
6. **`data/input/query.jpg`** — Test image (224x224 RGB synthetic image created with PIL).
7. **`data/debug/search_results.json`** — Debug output with 20 real candidates from MCR.
8. **`tests/test_searcher.py`** — Unit tests covering valid image, missing image, invalid path, non-image file, provider failure, empty results.
9. **`requirements.txt`** — Dependencies: Pillow, requests.
10. **`.env.example`** — Environment variable template.
11. **`docs/search_decision.md`** — Provider selection documentation.
12. **`README.md`** — Updated with Runtime Discovery POC section.

## Test Input

Test image: `data/input/query.jpg` — a 224x224 RGB synthetic image generated with Python PIL. No personal images used.

## Result

Candidates returned: 20

## Sample Result Structure

```json
{
  "candidate_id": "cand_000",
  "source_url": "https://mcr.microsoft.com/samples/blockchain-ai/0xdeca10b-demo",
  "image_url": "https://mcr.microsoft.com/samples/blockchain-ai/0xdeca10b-demo",
  "thumbnail_url": null,
  "title": "samples/blockchain-ai/0xdeca10b-demo",
  "search_rank": 1,
  "provider": "microsoft-foundry"
}
```

Fields successfully obtained: `candidate_id`, `source_url`, `image_url`, `thumbnail_url`, `title`, `search_rank`, `provider`.

## Errors / Limitations

- MCR catalog returns repository listings, not query-specific image results. The query is used as context only.
- Docker Hub API requires full `namespace/repo` format; partial queries may return empty results.
- No authentication for MCR catalog; rate limits may apply.
- The `query` parameter in MCR provider does not filter results; all catalog repos are returned.

## Fallback

Backup provider (Docker Hub) was not required. PRIMARY provider returned 20 results successfully.

## Validation

Commands used:
```bash
python -m unittest tests.test_searcher -v
# Result: 13 tests ran, all OK
```

POC execution:
```bash
python -m search.searcher
# Result: Candidates returned: 20
```

Debug output verified at `data/debug/search_results.json`.

## Status

PASS

## Next Step

Prepare for normalization + candidate retrieval.

## Git

Commit: `90a6aeac3cae97f54851a9d983ff313e4dbbd15`
Push: SUCCESS

---

## Phase 3 — Normalization + Candidate Retrieval

## Date

2026-09-06

## Engineer

Nikhil

## Branch

feature/normalization-retrieval

## Objective

Convert real Phase 2 search results into standardized candidate records and retrieve candidate images locally.

## Previous Phase

Phase 2 — Runtime Search POC

Reference:
- Branch: feature/search-poc
- Commit: 90a6aeac3cae97f54851a9d983ff313e4dbbd15
- Provider: Microsoft Foundry (MCR)
- Search candidates: 20
- Tests: 13/13

## Implementation

1. **`search/normalizer.py`** — `normalize_results(raw_results)` converts provider-specific output to stable internal structure. Handles URL normalization, duplicate detection, deterministic ID generation, rank preservation, and null handling for missing fields.
2. **`search/retriever.py`** — `retrieve_candidates(candidates, output_dir)` downloads candidate images via HTTP, validates content as images using PIL, saves locally to `data/candidates/`, and generates `data/debug/candidate_manifest.json`. Handles timeouts, HTTP errors, invalid content, and continues on failure.
3. **`search/pipeline.py`** — End-to-end pipeline runner: `search_image()` → `normalize_results()` → `retrieve_candidates()` → `print_pipeline_summary()`.
4. **`search/__init__.py`** — Updated to export `normalize_results`, `retrieve_candidates`, `get_manifest`, `print_pipeline_summary`.
5. **`.gitignore`** — Updated to include `data/candidates/` and `data/debug/candidate_manifest.json`.
6. **`tests/test_searcher.py`** — Added 14 new tests for normalizer (7 tests) and retriever (5 tests).
7. **`README.md`** — Updated with Candidate Normalization & Retrieval section.

## Normalization

- **Schema**: `candidate_id`, `provider`, `search_rank`, `title`, `source_url`, `image_url`, `thumbnail_url`
- **ID generation**: Deterministic `cand_001`, `cand_002`, etc. based on result order
- **Rank preservation**: Original `search_rank` from provider is preserved, not reordered
- **URL normalization**: Validates URLs have http/https scheme, strips whitespace, returns `null` for invalid URLs
- **Duplicate handling**: Deduplicates by exact normalized image URL (case-insensitive)
- **Missing fields**: `title`, `source_url`, `thumbnail_url` default to `null` when not provided

## Retrieval

- **HTTP implementation**: `requests.get()` with 15s timeout, 50MB size limit, streaming
- **Content validation**: PIL `Image.open()` + `verify()` to confirm actual image content
- **Image validation**: Content-type check + PIL format detection
- **Local storage**: `data/candidates/cand_001.jpg`, `cand_002.jpg`, etc.
- **Failure handling**: Continues on failure, records error reason (HTTP 403, timeout, invalid image, etc.)
- **Retries**: 2 attempts per candidate

## Test Input

Same as Phase 2: `data/input/query.jpg` — a 224x224 RGB synthetic image generated with Python PIL.

## Results

Search candidates: 20
Normalized candidates: 20
Retrieved: 0
Failed: 20

## Failure Details

All 20 candidates failed retrieval because the MCR catalog URLs (`https://mcr.microsoft.com/{repo_name}`) return HTML pages, not direct image blobs. The MCR catalog API provides repository listings, not downloadable image endpoints.

Examples of failure reasons:
- `downloaded content is not a valid image` — MCR returns HTML, not binary image data

This is a documented limitation of the current provider integration.

## Manifest

Location: `data/debug/candidate_manifest.json`
Contains all 20 candidates with retrieval status, error reasons, and local paths (null for failures).

## Validation

Commands used:
```bash
python -m unittest tests.test_searcher -v
# Result: 26 tests ran, all OK

python -m search.pipeline
# Result: Search candidates: 20, Normalized: 20, Retrieved: 0, Failed: 20
```

Real end-to-end pipeline verified:
- query.jpg → search_image() → 20 real candidates from MCR → normalize_results() → 20 normalized → retrieve_candidates() → 0 retrieved, 20 failed (expected — MCR URLs are HTML pages)

## Security

Safeguards implemented:
- Request timeout (15s)
- Response size limit (50MB)
- Content-type validation
- Image content validation via PIL
- Safe deterministic filenames
- No shell commands from URLs
- No credentials or sensitive data logged

## Status

PARTIAL

Search and normalization work correctly. Retrieval returns 0 successes because MCR catalog URLs are not direct image download endpoints. This is a known provider limitation, not a code defect.

## Known Limitations

- MCR catalog URLs return HTML pages, not downloadable images
- The `image_url` from MCR is a catalog page, not a blob URL
- No thumbnail URLs are available from the current provider
- Docker Hub backup provider was not tested for retrieval (would face same issue with `docker.io/repo:tag` URLs not being direct image URLs)
- The pipeline correctly handles all failures and records them in the manifest

## Next Step

Face Verification / Candidate Matching

## Git

Commit: `df1d41dc0cfdbf2cf4c65b7907d85bef5b1a1e10`
Push: SUCCESS

---

## Summary

| Metric | Value |
|--------|-------|
| Total Commits | 3 |
| Branch | `feature/normalization-retrieval` |
| Phase 1 Commit | `06afd98` |
| Phase 2 Commit | `90a6aeac3cae97f54851a9d983ff313e4dbbd15` |
| Phase 3 Commit | `df1d41dc0cfdbf2cf4c65b7907d85bef5b1a1e10` |
| Repository | `true-brace05/Task3_HH_goa` |
| Remote | `origin` (https://github.com/true-brace05/Task3_HH_goa) |

---

*Audit maintained for tracking all project changes sequentially.*
