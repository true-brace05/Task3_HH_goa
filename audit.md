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

## Summary

| Metric | Value |
|--------|-------|
| Total Commits | 2 |
| Branch | `feature/search-poc` |
| Phase 1 Commit | `06afd98` |
| Phase 2 Commit | `90a6aeac3cae97f54851a9d983ff313e4dbbd15` |
| Repository | `true-brace05/Task3_HH_goa` |
| Remote | `origin` (https://github.com/true-brace05/Task3_HH_goa) |

---

*Audit maintained for tracking all project changes sequentially.*
