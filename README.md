# Runtime Discovery POC

## Selected Primary Provider

**Microsoft Foundry (MCR)** — `mcr.microsoft.com`

The Microsoft Container Registry is used as the primary runtime image search provider. It provides real container image catalog data through the MCR v2 registry API.

## Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

No API keys are required for the MCR catalog endpoint.

## Running the POC

```python
from search.searcher import search_image, run_search_and_save

# Basic search
results = search_image("data/input/query.jpg")
print(f"Candidates: {len(results)}")

# With debug output
output = run_search_and_save("data/input/query.jpg")
```

Or run directly:

```bash
python -m search.searcher
```

## Expected Output

```
[SEARCH START]
Input: data/input/query.jpg
Provider: microsoft-foundry

[SEARCH COMPLETE]
Candidates returned: <N>
```

## Test Input

A test image is generated at `data/input/query.jpg` using Python PIL. It is a simple 224x224 RGB image.

## Current Limitations

- MCR catalog returns repository listings, not image-specific search results
- The search query is used as context; results are catalog-based
- No authentication required for MCR public catalog
- Rate limits may apply for large queries
- Docker Hub backup provider requires the repository to exist publicly

## Debug Output

Search results are saved to `data/debug/search_results.json`.

## Candidate Normalization & Retrieval

### What Phase 3 Does

Phase 3 transforms raw provider search results into standardized candidate records and attempts to retrieve candidate images locally.

### Normalized Candidate Schema

Each normalized candidate contains:
- `candidate_id` — Deterministic ID (e.g., `cand_001`)
- `provider` — Source provider name
- `search_rank` — Original rank from the provider (preserved, not reordered)
- `title` — Candidate title, or `null` if not provided
- `source_url` — Source page URL, or `null` if not provided
- `image_url` — Image URL, or `null` if invalid
- `thumbnail_url` — Thumbnail URL, or `null` if not provided

### Retrieval Behavior

- Downloads images via HTTP with timeout (15s), size limit (50MB), and content validation
- Validates downloaded content is actually an image using PIL
- Saves validated images to `data/candidates/`
- Continues on failure — a single inaccessible candidate does not stop the pipeline
- Records retrieval status (`success` or `failed`) and error reason for each candidate

### Local Output Directory

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

### Manifest

The candidate manifest at `data/debug/candidate_manifest.json` connects every candidate to its retrieval status and local file path.

### How to Run

```python
from search.pipeline import run_pipeline
run_pipeline()
```

Or directly:
```bash
python -m search.pipeline
```

### How Failures Are Represented

- `retrieval_status: "success"` with `local_path` set
- `retrieval_status: "failed"` with `error` describing the reason (e.g., `HTTP 403`, `downloaded content is not a valid image`)
- `local_path: null` for failed retrievals

### Current Limitations

- MCR catalog URLs return HTML pages, not direct image blobs — retrieval fails for all MCR candidates
- The `image_url` from MCR is a catalog page URL, not a downloadable image URL
- No image thumbnails are available from the current provider
- Candidate retrieval does not establish identity — downloading a candidate image does not mean it is the person being searched for

### Security Safeguards

- Request timeouts enforced
- Response size limited to 50MB
- Content-type validation
- Image content validation via PIL
- Safe deterministic filenames only
- No shell commands constructed from URLs
- No credentials logged
