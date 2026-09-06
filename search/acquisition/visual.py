import logging
from pathlib import Path
from typing import Dict, Any

import requests
from PIL import Image
from io import BytesIO

from search.acquisition.base import ImageAcquisitionProvider, AcquisitionResult

logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024
TIMEOUT = 15
RETRIES = 2


class VisualSearchAcquisitionProvider(ImageAcquisitionProvider):
    def __init__(self):
        self.name = "visual-search-acquisition"

    def can_acquire(self, candidate: dict) -> bool:
        if not candidate.get("image_url"):
            return False
        provider = candidate.get("provider", "")
        return provider in ("google-lens", "visual-search") or "google" in candidate.get("image_url", "")

    def acquire(self, candidate: dict) -> dict:
        candidate_id = candidate.get("candidate_id", "unknown")
        image_url = candidate.get("image_url", "")

        logger.info("Visual search acquisition for %s", candidate_id)

        for attempt in range(RETRIES):
            try:
                response = requests.get(
                    image_url,
                    timeout=TIMEOUT,
                    stream=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                response.raise_for_status()

                content_length = int(response.headers.get("content-length", 0))
                if content_length > MAX_SIZE:
                    return {
                        "candidate_id": candidate_id,
                        "status": "failed",
                        "error": f"Image too large ({content_length} bytes)",
                        "provider": self.name,
                        "file_size": content_length,
                    }

                content_type = response.headers.get("content-type", "")
                if "image" not in content_type:
                    return {
                        "candidate_id": candidate_id,
                        "status": "failed",
                        "error": f"Not an image (content-type: {content_type})",
                        "provider": self.name,
                        "content_type": content_type,
                    }

                content = response.content
                try:
                    img = Image.open(BytesIO(content))
                    img.verify()
                except Exception:
                    return {
                        "candidate_id": candidate_id,
                        "status": "failed",
                        "error": "Downloaded content is not a valid image",
                        "provider": self.name,
                    }

                return self._save_image(candidate, content, content_type, content_length)

            except requests.exceptions.Timeout:
                logger.warning("Timeout for %s (attempt %d/%d)", image_url, attempt + 1, RETRIES)
            except requests.exceptions.HTTPError as e:
                logger.warning("HTTP error for %s: %s", image_url, e)
                return {
                    "candidate_id": candidate_id,
                    "status": "failed",
                    "error": f"HTTP error: {e}",
                    "provider": self.name,
                }
            except requests.exceptions.RequestException as e:
                logger.warning("Request failed for %s: %s", image_url, e)
                return {
                    "candidate_id": candidate_id,
                    "status": "failed",
                    "error": f"Request failed: {e}",
                    "provider": self.name,
                }

        return {
            "candidate_id": candidate_id,
            "status": "failed",
            "error": "Max retries exceeded",
            "provider": self.name,
        }

    def _save_image(self, candidate: dict, content: bytes, content_type: str, size: int) -> dict:
        try:
            img = Image.open(BytesIO(content))
            fmt = img.format or "PNG"
            ext = fmt.lower()
        except Exception:
            ext = "bin"

        output_dir = Path("data/candidates")
        output_dir.mkdir(parents=True, exist_ok=True)
        local_path = output_dir / f"{candidate['candidate_id']}.{ext}"

        with open(local_path, "wb") as f:
            f.write(content)

        logger.info("Saved image to %s", local_path)
        return {
            "candidate_id": candidate["candidate_id"],
            "status": "success",
            "provider": self.name,
            "local_path": str(local_path),
            "content_type": content_type,
            "file_size": size,
            "source_url": candidate.get("source_url"),
            "image_url": candidate.get("image_url"),
        }
