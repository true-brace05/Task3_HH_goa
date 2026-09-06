import logging
import re
from urllib.parse import urlparse
from typing import List, Optional

logger = logging.getLogger(__name__)


def normalize_results(raw_results: list) -> list:
    if not raw_results:
        return []

    normalized = []
    seen_urls = set()

    for i, raw in enumerate(raw_results):
        if not isinstance(raw, dict):
            logger.warning("Skipping non-dict result at index %d", i)
            continue

        image_url = _normalize_url(raw.get("image_url"))
        source_url = _normalize_url(raw.get("source_url"))
        thumbnail_url = _normalize_url(raw.get("thumbnail_url"))
        title = raw.get("title")
        if title is not None and not isinstance(title, str):
            title = None

        if not image_url:
            logger.warning("Skipping candidate at rank %s: no image_url", raw.get("search_rank"))
            continue

        norm_url = image_url.strip().lower()
        if norm_url in seen_urls:
            logger.debug("Duplicate image_url skipped: %s", image_url)
            continue
        seen_urls.add(norm_url)

        candidate = {
            "candidate_id": f"cand_{i+1:03d}",
            "provider": raw.get("provider", "unknown"),
            "search_rank": raw.get("search_rank", i + 1),
            "title": title,
            "source_url": source_url if source_url else None,
            "image_url": image_url,
            "thumbnail_url": thumbnail_url if thumbnail_url else None,
        }
        normalized.append(candidate)

    logger.info("Normalized %d candidates from %d raw results", len(normalized), len(raw_results))
    return normalized


def _normalize_url(url) -> Optional[str]:
    if url is None:
        return None
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    return url


def _is_duplicate(image_url: str, seen_urls: set) -> bool:
    norm = image_url.strip().lower()
    return norm in seen_urls
