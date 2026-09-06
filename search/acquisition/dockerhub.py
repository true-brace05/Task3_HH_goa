import logging
from typing import Dict, Any, Optional

import requests
from PIL import Image
from io import BytesIO

from search.acquisition.base import ImageAcquisitionProvider, AcquisitionResult

logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024
TIMEOUT = 15
RETRIES = 2


class DockerHubAcquisitionProvider(ImageAcquisitionProvider):
    def __init__(self):
        self.name = "dockerhub-acquisition"
        self.registry = "docker.io"
        self.base_url = "https://hub.docker.com/v2/repositories"

    def can_acquire(self, candidate: dict) -> bool:
        if not candidate.get("image_url"):
            return False
        return candidate.get("provider") == "dockerhub" or "docker.io" in candidate.get("image_url", "")

    def acquire(self, candidate: dict) -> dict:
        candidate_id = candidate.get("candidate_id", "unknown")
        image_url = candidate.get("image_url", "")

        # Parse repository name from docker.io URL
        # e.g., docker.io/pytorch/pytorch:latest
        if "docker.io/" not in image_url:
            repo_name = image_url
        else:
            repo_name = image_url.replace("docker.io/", "").split(":")[0]

        logger.info("Docker Hub acquisition for repo: %s", repo_name)

        # Try to get the manifest from Docker Hub registry
        registry_url = "https://registry-1.docker.io/v2"
        try:
            manifest_url = f"{registry_url}/{repo_name}/manifests/latest"
            mr = requests.get(manifest_url, timeout=TIMEOUT)
            if mr.status_code == 401:
                return {
                    "candidate_id": candidate_id,
                    "status": "failed",
                    "error": "Docker Hub registry requires authentication",
                    "provider": self.name,
                }
            mr.raise_for_status()
            manifest = mr.json()
        except requests.RequestException as e:
            return {
                "candidate_id": candidate_id,
                "status": "failed",
                "error": f"Failed to access Docker Hub registry: {e}",
                "provider": self.name,
            }

        # Get blob
        layers = manifest.get("fsLayers", [])
        if not layers:
            return {
                "candidate_id": candidate_id,
                "status": "failed",
                "error": "No layers found in manifest",
                "provider": self.name,
            }

        blob_digest = layers[0]["blobSum"]
        blob_url = f"{registry_url}/{repo_name}/blobs/{blob_digest}"

        logger.info("Attempting to download blob from Docker Hub: %s", blob_url)

        for attempt in range(RETRIES):
            try:
                br = requests.get(blob_url, timeout=TIMEOUT, stream=True)
                br.raise_for_status()

                content_type = br.headers.get("content-type", "")
                content_length = int(br.headers.get("content-length", 0))

                if content_length > MAX_SIZE:
                    return {
                        "candidate_id": candidate_id,
                        "status": "failed",
                        "error": f"Blob too large ({content_length} bytes), likely a container image layer",
                        "provider": self.name,
                        "file_size": content_length,
                    }

                content = br.content
                try:
                    img = Image.open(BytesIO(content))
                    img.verify()
                    return self._save_image(candidate, content, content_type, content_length)
                except Exception:
                    return {
                        "candidate_id": candidate_id,
                        "status": "failed",
                        "error": "Blob is not a visual image — container image layer",
                        "provider": self.name,
                        "content_type": content_type,
                    }

            except requests.exceptions.Timeout:
                logger.warning("Timeout for blob %s (attempt %d/%d)", blob_url, attempt + 1, RETRIES)
            except requests.exceptions.HTTPError as e:
                logger.warning("HTTP error for blob %s: %s", blob_url, e)
                return {
                    "candidate_id": candidate_id,
                    "status": "failed",
                    "error": f"HTTP error: {e}",
                    "provider": self.name,
                }
            except requests.exceptions.RequestException as e:
                logger.warning("Request failed for blob %s: %s", blob_url, e)
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
        import os
        from pathlib import Path

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
        }
