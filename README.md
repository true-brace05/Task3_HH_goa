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
