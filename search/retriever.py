import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024  # 50MB
TIMEOUT = 15
RETRIES = 2


def retrieve_candidates(candidates: list, output_dir: str = "data/candidates") -> list:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    success_count = 0
    fail_count = 0

    for i, cand in enumerate(candidates):
        image_url = cand.get("image_url")
        if not image_url:
            cand["retrieval_status"] = "failed"
            cand["error"] = "missing image URL"
            cand["local_path"] = None
            manifest_entries.append(cand)
            fail_count += 1
            continue

        filename = f"cand_{i+1:03d}"
        local_path = _download_image(image_url, output_path, filename)

        if local_path:
            cand["retrieval_status"] = "success"
            cand["local_path"] = str(local_path)
            success_count += 1
        else:
            cand["retrieval_status"] = "failed"
            cand["local_path"] = None
            fail_count += 1

        manifest_entries.append(cand)

    manifest = {
        "query_image": None,
        "candidate_count": len(candidates),
        "retrieved_count": success_count,
        "failed_count": fail_count,
        "candidates": manifest_entries,
    }

    manifest_path = Path("data/debug/candidate_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("[RETRIEVAL] Success: %d, Failed: %d", success_count, fail_count)
    logger.info("[MANIFEST] Saved to: %s", manifest_path)

    for entry in manifest_entries:
        if entry["retrieval_status"] == "success":
            logger.info("  %s -> %s", entry["candidate_id"], entry["local_path"])
        else:
            logger.info("  %s -> FAILED: %s", entry["candidate_id"], entry.get("error", "unknown"))

    return manifest


def _download_image(url: str, output_dir: Path, filename: str) -> Optional[Path]:
    for attempt in range(RETRIES):
        try:
            response = requests.get(
                url,
                timeout=TIMEOUT,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_SIZE:
                logger.warning("Skipping %s: too large (%s bytes)", url, content_length)
                return None

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type and not response.content:
                logger.warning("Skipping %s: not an image (content-type: %s)", url, content_type)
                return None

            try:
                img = Image.open(BytesIO(response.content))
                img.verify()
            except Exception:
                logger.warning("Skipping %s: downloaded content is not a valid image", url)
                return None

            ext = _get_extension(response.content, content_type)
            local_file = output_dir / f"{filename}.{ext}"

            with open(local_file, "wb") as f:
                f.write(response.content)

            logger.info("Downloaded %s -> %s", url, local_file)
            return local_file

        except requests.exceptions.Timeout:
            logger.warning("Timeout for %s (attempt %d/%d)", url, attempt + 1, RETRIES)
        except requests.exceptions.HTTPError as e:
            logger.warning("HTTP error for %s: %s (attempt %d/%d)", url, e, attempt + 1, RETRIES)
            if e.response.status_code in (403, 404):
                return None
        except requests.exceptions.ConnectionError:
            logger.warning("Connection error for %s (attempt %d/%d)", url, attempt + 1, RETRIES)
        except requests.exceptions.RequestException as e:
            logger.warning("Request failed for %s: %s", url, e)
            return None

    return None


def _get_extension(content: bytes, content_type: str) -> str:
    try:
        img = Image.open(BytesIO(content))
        fmt = img.format
        if fmt:
            return fmt.lower()
    except Exception:
        pass
    if "jpeg" in content_type:
        return "jpg"
    if "png" in content_type:
        return "png"
    if "gif" in content_type:
        return "gif"
    if "webp" in content_type:
        return "webp"
    return "bin"


def get_manifest(manifest_path: str = "data/debug/candidate_manifest.json") -> dict:
    with open(manifest_path) as f:
        return json.load(f)


def print_pipeline_summary(manifest: dict):
    candidate_count = manifest.get('candidate_count', 0)
    success_count = manifest.get('retrieved_count', manifest.get('acquired_count', 0))
    fail_count = manifest.get('failed_count', 0)
    print(f"\n[SEARCH] Candidates discovered: {candidate_count}")
    print(f"[NORMALIZATION] Candidates normalized: {candidate_count}")
    print(f"[ACQUISITION] Successfully acquired: {success_count}")
    print(f"[ACQUISITION] Failed: {fail_count}")
    print(f"[MANIFEST] Saved: data/debug/candidate_manifest.json")
