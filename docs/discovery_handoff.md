# Discovery Module — Handoff to Member 1 (Face Verification)

## Overview

This document describes the Discovery Module's contract, usage, and limitations for integration with Member 1's face-verification pipeline.

## What Discovery Produces

### Input

A local image file path (e.g., `data/input/query.jpg`).

### Output

A `dict` with the following structure:

```python
{
    "query_image": "query.jpg",
    "candidate_count": 20,
    "acquisition_attempted": 20,
    "acquired_count": 19,
    "failed_count": 1,
    "timestamp": "2026-09-06T12:00:00+00:00",
    "candidates": [
        {
            "candidate_id": "cand_001",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_001.jpeg",
            "content_type": "image/jpeg",
            "file_size": 15956,
            "content_sha256": "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95",
            "source_url": "https://...",
            "image_url": "https://...",
            "thumbnail_url": null,
            "title": null,
            "search_rank": 1,
            "discovery_provider": "yandex-visual-search"
        },
        ...
    ]
}
```

### Candidate Contract

Each candidate dict contains:

| Field | Type | Description |
|-------|------|-------------|
| `candidate_id` | `str` | Deterministic ID (`cand_001`, `cand_002`, ...) |
| `status` | `str` | `"success"` or `"failed"` |
| `provider` | `str` | Acquisition provider name |
| `local_path` | `str` or `null` | Local file path (only on success) |
| `content_type` | `str` or `null` | HTTP content-type (only on success) |
| `file_size` | `int` or `null` | File size in bytes (only on success) |
| `content_sha256` | `str` or `null` | SHA-256 hash of image bytes (only on success) |
| `source_url` | `str` or `null` | Original source URL from visual search |
| `image_url` | `str` or `null` | Image URL from visual search |
| `thumbnail_url` | `str` or `null` | Thumbnail URL (if available) |
| `title` | `str` or `null` | Page title (if available) |
| `search_rank` | `int` | Rank from visual search (1-indexed) |
| `discovery_provider` | `str` | Discovery provider name |
| `error` | `str` or `null` | Error message (only on failure) |

## How to Run

### Full Pipeline

```python
from search.acquisition.runner import run_pipeline

manifest = run_pipeline("data/input/query.jpg")
print(f"Candidates: {manifest['acquired_count']}")
```

### Search Only (No Download)

```python
from search.searcher import search_image

candidates = search_image("data/input/query.jpg")
print(f"Found: {len(candidates)} candidates")
```

### CLI

```bash
python -m search.visual.runner
```

## Dependencies

```
Pillow>=10.0.0
requests>=2.28.0
beautifulsoup4>=4.12.0
```

## Key Files

| File | Purpose |
|------|---------|
| `search/searcher.py` | Entry point: `search_image()` |
| `search/visual/yandex.py` | Primary visual search provider |
| `search/visual/google_lens.py` | Backup provider (blocked by CAPTCHA) |
| `search/normalizer.py` | URL normalization, deduplication, deterministic IDs |
| `search/acquisition/visual.py` | Image download, validation, SHA-256 |
| `search/acquisition/runner.py` | Full pipeline orchestration |
| `search/acquisition/base.py` | `AcquisitionManager` abstraction |

## Provenance Chain

```
search_image() → YandexVisualSearchProvider → raw candidates
    ↓
normalize_results() → deterministic IDs, deduplication
    ↓
run_acquisition_pipeline() → download, validate, SHA-256
    ↓
candidate_manifest.json → complete provenance
```

## Known Limitations

1. **Yandex is a public web interface**, not an official API. Subject to rate limiting and availability changes.
2. **Some image hosts timeout** during acquisition (typically 1 of 20).
3. **Title and thumbnail_url are often null** — Yandex doesn't always provide these.
4. **No face detection** — Discovery returns all visually similar images, not just faces.
5. **CAPTCHA possible** — If Yandex blocks requests, provider returns empty list.

## What Member 1 Should Know

1. **Use `local_path`** from successful candidates for face verification.
2. **Use `content_sha256`** for deduplication across runs.
3. **Use `search_rank`** to prioritize candidates (lower rank = more similar).
4. **Filter by `status`** — only `"success"` candidates have `local_path`.
5. **`title` and `thumbnail_url` may be null** — don't depend on them.
6. **`source_url`** is the original web page where the image was found.
7. **`image_url`** is the direct image URL that was downloaded.

## Test Results

- **51 unit tests**, all passing
- **E2E pipeline**: 20 candidates → 19 acquired → SHA-256 computed
- **Manifest**: `data/debug/candidate_manifest.json`

## Contact

Member 2 (Nikhil) — Discovery Module
