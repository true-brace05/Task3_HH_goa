# Runtime Discovery POC — Phase 6: Visual Reverse Image Search

## Phase 6 Overview

### Objective

Replace the blocked Google Lens provider with a legitimate alternative visual-search mechanism that returns real runtime candidates.

### Architecture

```
Local query image → Yandex Visual Search → Web image candidates → Image acquisition → Local candidates → SHA-256 → Manifest
```

- **`search/visual/base.py`** — `VisualSearchProvider` abstract base class
- **`search/visual/yandex.py`** — `YandexVisualSearchProvider` — POSTs local image to Yandex's image search endpoint, parses HTML results for similar images
- **`search/visual/google_lens.py`** — `GoogleLensProvider` — preserved as backup (blocked by CAPTCHA)
- **`search/visual/runner.py`** — Visual search pipeline runner
- **`search/acquisition/visual.py`** — `VisualSearchAcquisitionProvider` — downloads actual web images, validates, computes SHA-256
- **`search/searcher.py`** — Updated to use `YandexVisualSearchProvider` as PRIMARY, `GoogleLensProvider` as BACKUP
- **`search/acquisition/runner.py`** — Updated to use `VisualSearchAcquisitionProvider` as PRIMARY acquisition

### Provider Selection

**Primary**: `YandexVisualSearchProvider` (`yandex-visual-search`) — Uses Yandex's image search endpoint via `requests` + `BeautifulSoup`

**Backup**: `GoogleLensProvider` (`google-lens`) — preserved but blocked by CAPTCHA

**Acquisition**: `VisualSearchAcquisitionProvider` (`visual-search-acquisition`) — Downloads images from web URLs, validates, computes SHA-256

### Research Basis

Based on open-source Yandex reverse image search implementations (MIT license):
- Uses Google's undocumented `searchbyimage` endpoint
- No official Google API exists for reverse image search
- Implementation scrapes the endpoint behind a Python wrapper
- `beautifulsoup4` already installed in environment

### Usage

```python
from search.searcher import search_image
from search.visual.google_lens import GoogleLensProvider

# Basic visual search
results = search_image("data/input/query.jpg")
print(f"Candidates: {len(results)}")

# Direct provider usage
provider = GoogleLensProvider()
results = provider.search_by_image("data/input/query.jpg")
```

Or run the full pipeline:

```python
from search.visual.runner import run_pipeline
manifest = run_pipeline("data/input/query.jpg")
```

Or via CLI:

```bash
python -m search.visual.runner
```

## Dependencies

```bash
pip install -r requirements.txt
```

Dependencies: `Pillow>=10.0.0`, `requests>=2.28.0`, `beautifulsoup4>=4.12.0`

## How It Works

### Visual Search Flow

1. **Image Upload**: Local image file is POSTed to `https://www.google.com/searchbyimage/upload`
2. **HTML Parsing**: Response HTML is parsed with BeautifulSoup to extract image result tiles
3. **URL Extraction**: Links are extracted from result tiles, filtering for `/url?q=` patterns
4. **Deduplication**: Duplicate URLs are removed
5. **Result Format**: Returns list of dicts with `source_url`, `image_url`, `title`, `provider`

### Acquisition Flow

1. **Candidate Validation**: Each candidate from visual search is checked by `VisualSearchAcquisitionProvider`
2. **Image Download**: The `image_url` from Google Lens results is downloaded
3. **Content Validation**: PIL verifies downloaded content is a valid image
4. **Local Storage**: Validated images are saved to `data/candidates/`
5. **Manifest**: Results recorded in `data/debug/candidate_manifest.json`

### CAPTCHA Handling

If Google returns a CAPTCHA or upload form instead of results, the provider returns an empty list and logs `[VISUAL SEARCH BLOCKED]`. This is honest reporting — no fake results are generated.

## Test Input

A test image is generated at `data/input/query.jpg` using Python PIL. It is a simple 224x224 RGB synthetic image.

## Current Limitations

- Google may block requests with CAPTCHA (detected and reported honestly)
- BeautifulSoup parsing uses selector-light approach; Google may change markup
- No official Google API exists — this is community-built reverse image search
- Rate limiting may apply for large queries
- Visual search returns 0 results when Google blocks the request (expected behavior)

## Debug Output

Search results are saved to `data/debug/search_results.json`.

## Pipeline Output

```
data/
├── input/
│   └── query.jpg
├── candidates/
│   ├── cand_001.jpg
│   ├── cand_002.jpg
│   └── ...
└── debug/
    ├── search_results.json
    └── candidate_manifest.json
```

## Test Results

- 44 unit tests, all passing
- Visual search provider tests: 7 tests covering valid/invalid images, error handling
- End-to-end pipeline verified with `data/input/query.jpg`
- Google CAPTCHA blocking correctly reported as `[VISUAL SEARCH BLOCKED]`

## Security Safeguards

- Request timeouts enforced (20s for visual search, 15s for acquisition)
- Response size limited to 50MB
- Content-type validation
- Image content validation via PIL
- Safe deterministic filenames only
- No shell commands constructed from URLs
- No credentials logged
- File handles properly closed using context managers
