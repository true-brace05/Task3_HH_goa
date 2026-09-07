import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class ImageAcquisitionProvider(ABC):
    def __init__(self):
        self.name = "base"

    @abstractmethod
    def acquire(self, candidate: dict) -> dict:
        pass

    @abstractmethod
    def can_acquire(self, candidate: dict) -> bool:
        pass


class AcquisitionResult:
    def __init__(self, candidate_id: str, status: str, **kwargs):
        self.candidate_id = candidate_id
        self.status = status
        self.local_path = kwargs.get("local_path")
        self.error = kwargs.get("error")
        self.content_type = kwargs.get("content_type")
        self.file_size = kwargs.get("file_size")
        self.provider = kwargs.get("provider", "unknown")
        self.source_url = kwargs.get("source_url")
        self.image_url = kwargs.get("image_url")

    def to_dict(self) -> dict:
        result = {
            "candidate_id": self.candidate_id,
            "acquisition_status": self.status,
            "provider": self.provider,
            "source_url": self.source_url,
            "image_url": self.image_url,
            "local_path": self.local_path,
        }
        if self.error:
            result["error"] = self.error
        if self.content_type:
            result["content_type"] = self.content_type
        if self.file_size:
            result["file_size"] = self.file_size
        return result


class AcquisitionManager:
    def __init__(self, primary_provider: ImageAcquisitionProvider, backup_provider: Optional[ImageAcquisitionProvider] = None):
        self.primary = primary_provider
        self.backup = backup_provider

    def acquire(self, candidate: dict) -> dict:
        logger.info("Acquiring candidate %s with %s", candidate.get("candidate_id"), self.primary.name)
        try:
            if self.primary.can_acquire(candidate):
                result = self.primary.acquire(candidate)
                logger.info("Acquisition result for %s: %s", candidate["candidate_id"], result["status"])
                return result
        except Exception as e:
            logger.warning("Primary acquisition failed for %s: %s", candidate.get("candidate_id"), e)

        if self.backup:
            logger.info("Falling back to backup provider: %s", self.backup.name)
            try:
                if self.backup.can_acquire(candidate):
                    result = self.backup.acquire(candidate)
                    logger.info("Backup acquisition result for %s: %s", candidate["candidate_id"], result["status"])
                    return result
            except Exception as e:
                logger.warning("Backup acquisition failed for %s: %s", candidate.get("candidate_id"), e)

        return {
            "candidate_id": candidate.get("candidate_id"),
            "status": "failed",
            "error": "No acquisition provider available",
            "provider": "none",
        }

    def acquire_batch(self, candidates: list) -> list:
        results = []
        for candidate in candidates:
            result = self.acquire(candidate)
            results.append(result)
        return results
