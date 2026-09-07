"""Evidence schema definitions for Phase 1.

Uses dataclasses with explicit validation to avoid introducing new
dependencies. Validation mirrors the spec:

- image_url must be http/https
- content_sha256 must be 64 hex chars when present
- status must be success|failed
- event must be one of allowed events
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from urllib.parse import urlparse


ALLOWED_STATUSES = {"success", "failed"}
ALLOWED_EVENTS = {
    "discovery_complete",
    "normalization_complete",
    "acquisition_complete",
    "verification_complete",
    "evidence_built",
    "blockchain_registered",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_url(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str or None, got {type(value).__name__}")
    value = value.strip()
    if value == "":
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{field_name} must be http or https URL, got: {value!r}")
    return value


def _validate_sha256(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"content_sha256 must be str or None, got {type(value).__name__}")
    if not SHA256_RE.match(value):
        raise ValueError(f"content_sha256 must be 64 hex chars, got: {value!r}")
    return value.lower()


def _validate_status(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"status must be str, got {type(value).__name__}")
    if value not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of {ALLOWED_STATUSES}, got: {value!r}")
    return value


def _validate_event(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"event must be str, got {type(value).__name__}")
    if value not in ALLOWED_EVENTS:
        raise ValueError(f"event must be one of {ALLOWED_EVENTS}, got: {value!r}")
    return value


ALLOWED_DECISIONS = {"match", "no_match", "inconclusive", "error"}


def _validate_decision(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"decision must be str or None, got {type(value).__name__}")
    if value not in ALLOWED_DECISIONS:
        raise ValueError(f"decision must be one of {ALLOWED_DECISIONS}, got: {value!r}")
    return value


@dataclass
class VerificationData:
    """Structured verification data for a candidate.

    Score is stored as deterministic decimal string (e.g. "0.873421") with explicit
    precision to avoid canonical JSON float rejection. See evidence.canonical.
    """

    method: str = "pending"
    score: Optional[str] = None  # deterministic string, not float
    decision: Optional[str] = None  # match|no_match|inconclusive|error
    timestamp: Optional[str] = None
    query_face_detected: Optional[bool] = None
    candidate_face_detected: Optional[bool] = None
    error: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.method, str) or not self.method:
            raise ValueError(f"verification.method must be non-empty str, got {type(self.method).__name__}")
        if self.score is not None:
            if not isinstance(self.score, str):
                # For backward compat, allow float/int but convert deterministically
                # Conversion happens here with fixed 6 decimals if numeric
                if isinstance(self.score, (int, float)):
                    self.score = f"{float(self.score):.6f}"
                else:
                    raise ValueError(f"verification.score must be str or None, got {type(self.score).__name__}")
            else:
                # validate string is numeric decimal
                if self.score.strip() == "":
                    raise ValueError("verification.score string must not be empty")
                # allow decimal string, check it parses as float
                try:
                    float(self.score)
                except ValueError:
                    raise ValueError(f"verification.score string must be numeric, got: {self.score!r}")
        self.decision = _validate_decision(self.decision)
        if self.timestamp is not None and not isinstance(self.timestamp, str):
            raise ValueError(f"verification.timestamp must be str or None, got {type(self.timestamp).__name__}")
        if self.query_face_detected is not None and not isinstance(self.query_face_detected, bool):
            raise ValueError(f"query_face_detected must be bool or None, got {type(self.query_face_detected).__name__}")
        if self.candidate_face_detected is not None and not isinstance(self.candidate_face_detected, bool):
            raise ValueError(f"candidate_face_detected must be bool or None, got {type(self.candidate_face_detected).__name__}")
        if self.error is not None and not isinstance(self.error, str):
            raise ValueError(f"error must be str or None, got {type(self.error).__name__}")

    def to_dict(self) -> dict:
        # Always include all keys deterministically for canonical hashing
        return {
            "method": self.method,
            "score": self.score,
            "decision": self.decision,
            "timestamp": self.timestamp,
            "query_face_detected": self.query_face_detected,
            "candidate_face_detected": self.candidate_face_detected,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VerificationData":
        if not isinstance(d, dict):
            raise ValueError("verification must be dict")
        return cls(
            method=d.get("method", "pending"),
            score=d.get("score"),
            decision=d.get("decision"),
            timestamp=d.get("timestamp"),
            query_face_detected=d.get("query_face_detected"),
            candidate_face_detected=d.get("candidate_face_detected"),
            error=d.get("error"),
        )


@dataclass
class CandidateEvidence:
    candidate_id: str
    image_url: str
    discovery_provider: str
    search_rank: int
    status: str
    local_path: Optional[str] = None
    content_sha256: Optional[str] = None
    source_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    title: Optional[str] = None
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    evidence_hash: Optional[str] = None
    verification: VerificationData = field(default_factory=VerificationData)

    def __post_init__(self):
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise ValueError("candidate_id must be non-empty str")
        self.image_url = _validate_url(self.image_url, "image_url")  # type: ignore
        if self.image_url is None:
            raise ValueError("image_url is required and must be http/https")
        self.source_url = _validate_url(self.source_url, "source_url")
        self.thumbnail_url = _validate_url(self.thumbnail_url, "thumbnail_url")
        self.content_sha256 = _validate_sha256(self.content_sha256)
        self.status = _validate_status(self.status)
        if not isinstance(self.discovery_provider, str) or not self.discovery_provider:
            raise ValueError("discovery_provider must be non-empty str")
        if not isinstance(self.search_rank, int) or self.search_rank < 1:
            raise ValueError("search_rank must be int >=1")
        if self.file_size is not None and not isinstance(self.file_size, int):
            raise ValueError("file_size must be int or None")
        if self.evidence_hash is not None:
            if not isinstance(self.evidence_hash, str) or not SHA256_RE.match(self.evidence_hash):
                raise ValueError(f"evidence_hash must be 64 hex chars or None, got: {self.evidence_hash!r}")
            self.evidence_hash = self.evidence_hash.lower()
        if isinstance(self.verification, dict):
            self.verification = VerificationData.from_dict(self.verification)
        if not isinstance(self.verification, VerificationData):
            raise ValueError("verification must be VerificationData or dict")

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "local_path": self.local_path,
            "content_sha256": self.content_sha256,
            "source_url": self.source_url,
            "image_url": self.image_url,
            "thumbnail_url": self.thumbnail_url,
            "title": self.title,
            "discovery_provider": self.discovery_provider,
            "search_rank": self.search_rank,
            "status": self.status,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "evidence_hash": self.evidence_hash,
            "verification": self.verification.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CandidateEvidence":
        if not isinstance(d, dict):
            raise ValueError("CandidateEvidence must be dict")
        ver = d.get("verification", {"method": "pending", "score": None, "timestamp": None})
        if isinstance(ver, dict):
            ver = VerificationData.from_dict(ver)
        return cls(
            candidate_id=d["candidate_id"],
            local_path=d.get("local_path"),
            content_sha256=d.get("content_sha256"),
            source_url=d.get("source_url"),
            image_url=d["image_url"],
            thumbnail_url=d.get("thumbnail_url"),
            title=d.get("title"),
            discovery_provider=d.get("discovery_provider", "unknown"),
            search_rank=d.get("search_rank", 1),
            status=d.get("status", "success"),
            file_size=d.get("file_size"),
            content_type=d.get("content_type"),
            evidence_hash=d.get("evidence_hash"),
            verification=ver,
        )


@dataclass
class TimelineEvent:
    ts: str
    event: str
    detail: dict = field(default_factory=dict)
    actor: str = "system"

    def __post_init__(self):
        if not isinstance(self.ts, str) or not self.ts:
            raise ValueError("ts must be non-empty str (ISO8601)")
        self.event = _validate_event(self.event)
        if not isinstance(self.detail, dict):
            raise ValueError("detail must be dict")
        if not isinstance(self.actor, str) or not self.actor:
            raise ValueError("actor must be non-empty str")

    def to_dict(self) -> dict:
        return {"ts": self.ts, "event": self.event, "detail": self.detail, "actor": self.actor}

    @classmethod
    def from_dict(cls, d: dict) -> "TimelineEvent":
        if not isinstance(d, dict):
            raise ValueError("TimelineEvent must be dict")
        return cls(ts=d["ts"], event=d["event"], detail=d.get("detail", {}), actor=d.get("actor", "system"))


@dataclass
class EvidenceEnvelope:
    envelope_version: str = "1.0"
    query_image: Optional[str] = None
    manifest_timestamp: Optional[str] = None
    created_at: str = ""
    pipeline_run_id: str = ""
    candidate_count: int = 0
    acquired_count: int = 0
    evidence_hash: Optional[str] = None
    candidates: List[CandidateEvidence] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)

    def __post_init__(self):
        if self.envelope_version != "1.0":
            raise ValueError("envelope_version must be '1.0'")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("created_at must be non-empty ISO8601 str")
        if not isinstance(self.pipeline_run_id, str) or not self.pipeline_run_id:
            raise ValueError("pipeline_run_id must be non-empty str")
        if not isinstance(self.candidate_count, int) or self.candidate_count < 0:
            raise ValueError("candidate_count must be int >=0")
        if not isinstance(self.acquired_count, int) or self.acquired_count < 0:
            raise ValueError("acquired_count must be int >=0")
        if self.evidence_hash is not None and not SHA256_RE.match(self.evidence_hash):
            raise ValueError(f"evidence_hash must be 64 hex or None, got: {self.evidence_hash!r}")
        if self.evidence_hash is not None:
            self.evidence_hash = self.evidence_hash.lower()
        # ensure candidates/timeline are proper objects
        for c in self.candidates:
            if not isinstance(c, CandidateEvidence):
                raise ValueError("candidates must be List[CandidateEvidence]")
        for t in self.timeline:
            if not isinstance(t, TimelineEvent):
                raise ValueError("timeline must be List[TimelineEvent]")

    def to_dict(self) -> dict:
        return {
            "envelope_version": self.envelope_version,
            "query_image": self.query_image,
            "manifest_timestamp": self.manifest_timestamp,
            "created_at": self.created_at,
            "pipeline_run_id": self.pipeline_run_id,
            "candidate_count": self.candidate_count,
            "acquired_count": self.acquired_count,
            "evidence_hash": self.evidence_hash,
            "candidates": [c.to_dict() for c in self.candidates],
            "timeline": [t.to_dict() for t in self.timeline],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceEnvelope":
        if not isinstance(d, dict):
            raise ValueError("EvidenceEnvelope must be dict")
        cands = [CandidateEvidence.from_dict(c) for c in d.get("candidates", [])]
        timeline = [TimelineEvent.from_dict(t) for t in d.get("timeline", [])]
        return cls(
            envelope_version=d.get("envelope_version", "1.0"),
            query_image=d.get("query_image"),
            manifest_timestamp=d.get("manifest_timestamp"),
            created_at=d.get("created_at", ""),
            pipeline_run_id=d.get("pipeline_run_id", ""),
            candidate_count=d.get("candidate_count", len(cands)),
            acquired_count=d.get("acquired_count", 0),
            evidence_hash=d.get("evidence_hash"),
            candidates=cands,
            timeline=timeline,
        )
