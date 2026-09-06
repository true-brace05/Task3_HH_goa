import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import requests

from search.visual.google_lens import GoogleLensProvider

logger = logging.getLogger(__name__)

PRIMARY_PROVIDER = GoogleLensProvider()
BACKUP_PROVIDER = None


def _validate_image(image_path: str) -> Path:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {image_path}")

    valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}
    if path.suffix.lower() not in valid_extensions:
        raise ValueError(
            f"Unsupported image format: {path.suffix}. "
            f"Supported formats: {', '.join(sorted(valid_extensions))}"
        )

    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
    except Exception as e:
        raise ValueError(f"File is not a valid image: {e}")

    return path


def search_image(image_path: str) -> List[dict]:
    logger.info("[SEARCH START] Input: %s", image_path)

    try:
        path = _validate_image(image_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error("[SEARCH FAILED] Reason: %s", e)
        raise

    logger.info("Validated image: %s", path.name)
    logger.info("Invoking PRIMARY provider: %s", PRIMARY_PROVIDER.name)

    try:
        candidates = PRIMARY_PROVIDER.search_by_image(str(path))
        logger.info("PRIMARY returned %d candidates", len(candidates))
    except Exception as e:
        logger.warning("PRIMARY provider failed: %s", e)
        logger.error("[SEARCH FAILED] Visual search provider failed: %s", e)
        return []

    if not candidates:
        logger.info("[SEARCH COMPLETE] Candidates returned: 0")
        return []

    results = []
    for i, cand in enumerate(candidates):
        result = {
            "candidate_id": f"cand_{i:03d}",
            "source_url": cand.get("source_url"),
            "image_url": cand.get("image_url"),
            "thumbnail_url": cand.get("thumbnail_url"),
            "title": cand.get("title"),
            "search_rank": i + 1,
            "provider": cand.get("provider", PRIMARY_PROVIDER.name),
        }
        results.append(result)

    logger.info("[SEARCH COMPLETE] Candidates returned: %d", len(results))
    return results


def run_search_and_save(image_path: str, output_path: str = "data/debug/search_results.json"):
    path = Path(image_path)
    candidates = search_image(image_path)

    output = {
        "query_image": path.name,
        "provider": PRIMARY_PROVIDER.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("Debug output saved to: %s", output_path)
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = run_search_and_save("data/input/query.jpg")
    print(f"\nCandidates returned: {result['candidate_count']}")
