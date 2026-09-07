"""Evidence builder — pure function from acquisition manifest to EvidenceEnvelope.

Manifest contract (from acquisition runner run_acquisition_pipeline):
  {
    "query_image": str | None,
    "candidate_count": int,
    "acquisition_attempted": int,
    "acquired_count": int,
    "failed_count": int,
    "timestamp": ISO8601 str,
    "candidates": [
      {
        "candidate_id": str,
        "status": "success"|"failed",
        "provider": str (acquisition provider, e.g. visual-search-acquisition),
        "local_path": str|None,
        "content_type": str|None,
        "file_size": int|None,
        "content_sha256": str|None (64 hex, only on success),
        "source_url": str|None,
        "image_url": str|None,
        "thumbnail_url": str|None,
        "title": str|None,
        "search_rank": int,
        "discovery_provider": str (e.g. yandex-visual-search),
        "error": str|None (only on failure)
      }
    ]
  }

Also tolerates retriever manifest (retrieved_count, retrieval_status) for robustness.

This module has zero dependency on discovery code — it consumes manifest output only.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

from evidence.schema import CandidateEvidence, EvidenceEnvelope, TimelineEvent, VerificationData
from evidence.timeline import create_timeline_event
from evidence.hash import hash_candidate, hash_envelope
from evidence.canonical import canonical_dumps


def _load_manifest(manifest: Union[dict, str, Path]) -> dict:
    if isinstance(manifest, dict):
        return manifest
    # path-like
    path = Path(manifest)  # type: ignore[arg-type]
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Manifest JSON must be an object")
    return data


def _map_candidate(raw: dict) -> CandidateEvidence:
    """Map a manifest candidate dict to CandidateEvidence.

    Preserves acquisition metadata; handles both success/failed.
    Requires image_url to be present and valid http/https.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"candidate must be dict, got {type(raw).__name__}")

    candidate_id = raw.get("candidate_id", "cand_000")
    # acquisition runner uses image_url, source_url, etc. directly
    image_url = raw.get("image_url")
    if not image_url:
        raise ValueError(f"candidate {candidate_id} missing image_url")

    # discovery_provider may be in discovery_provider or provider field
    # manifest's provider = acquisition provider, discovery_provider = original search provider
    discovery_provider = raw.get("discovery_provider") or raw.get("provider") or "unknown"

    # status may be "status" (acquisition) or "retrieval_status" (retriever)
    status = raw.get("status") or raw.get("retrieval_status") or raw.get("acquisition_status") or "failed"
    # normalize to success/failed
    if status not in ("success", "failed"):
        # retriever uses success/failed already; other values -> failed
        status = "failed" if status != "success" else "success"

    # search_rank
    try:
        search_rank = int(raw.get("search_rank", 1))
    except Exception:
        search_rank = 1

    # verification: if manifest already contains structured verification (from face step), preserve it
    raw_ver = raw.get("verification")
    if isinstance(raw_ver, dict):
        try:
            verification = VerificationData.from_dict(raw_ver)
        except Exception:
            verification = VerificationData(method="pending", score=None, decision=None, timestamp=None)
    elif isinstance(raw_ver, VerificationData):
        verification = raw_ver
    else:
        verification = VerificationData(method="pending", score=None, decision=None, timestamp=None)

    cand = CandidateEvidence(
        candidate_id=str(candidate_id),
        local_path=raw.get("local_path"),
        content_sha256=raw.get("content_sha256"),
        source_url=raw.get("source_url"),
        image_url=str(image_url),
        thumbnail_url=raw.get("thumbnail_url"),
        title=raw.get("title"),
        discovery_provider=str(discovery_provider),
        search_rank=search_rank,
        status=str(status),
        file_size=raw.get("file_size"),
        content_type=raw.get("content_type"),
        evidence_hash=None,
        verification=verification,
    )
    # For failed candidates keep evidence_hash = None per spec
    # For success compute hash later after object creation
    return cand


def build_evidence(
    manifest: Union[dict, str, Path],
    query_image: Optional[str] = None,
    timeline: Optional[List[TimelineEvent]] = None,
    created_at: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    output_dir: Optional[Union[str, Path]] = None,
    write_files: bool = True,
) -> EvidenceEnvelope:
    """Build EvidenceEnvelope from manifest.

    Args:
        manifest: dict or path to JSON file (real output of run_acquisition_pipeline).
        query_image: override query image name; else from manifest.
        timeline: optional existing timeline events (TimelineEvent list or dict list).
        created_at: ISO8601 UTC timestamp; if None generated now.
        pipeline_run_id: UUID string; if None generated via uuid4.
        output_dir: directory for evidence files (default data/evidence).
        write_files: if True write pretty + canonical JSON files.

    Returns:
        EvidenceEnvelope with candidate evidence_hash and root evidence_hash computed.

    The function is pure except for file writes when write_files=True.
    """
    data = _load_manifest(manifest)

    # Extract manifest fields
    manifest_query = data.get("query_image")
    manifest_timestamp = data.get("timestamp") or data.get("manifest_timestamp")

    if query_image is None:
        query_image = manifest_query

    candidates_raw: List[dict] = data.get("candidates", [])
    if not isinstance(candidates_raw, list):
        raise ValueError("manifest candidates must be list")

    candidate_count = data.get("candidate_count", len(candidates_raw))
    acquired_count = data.get("acquired_count", data.get("retrieved_count", 0))

    # Build timeline: normalize input
    normalized_timeline: List[TimelineEvent] = []
    if timeline is not None:
        for item in timeline:
            if isinstance(item, TimelineEvent):
                normalized_timeline.append(item)
            elif isinstance(item, dict):
                normalized_timeline.append(TimelineEvent.from_dict(item))
            else:
                raise TypeError(f"timeline item must be TimelineEvent or dict, got {type(item).__name__}")

    # If no timeline provided, create minimal provenance events for Phase 1
    # These are not hash-critical beyond their inclusion; they document pipeline
    if not normalized_timeline:
        # acquisition_complete event derived from manifest
        ts = manifest_timestamp or datetime.now(timezone.utc).isoformat()
        normalized_timeline.append(
            create_timeline_event(
                "acquisition_complete",
                detail={
                    "candidate_count": candidate_count,
                    "acquired_count": acquired_count,
                    "failed_count": data.get("failed_count", 0),
                },
                actor="acquisition",
                ts=ts,
            )
        )

    # Map candidates
    candidates: List[CandidateEvidence] = []
    for raw in candidates_raw:
        # skip non-dicts (defensive)
        if not isinstance(raw, dict):
            continue
        try:
            cand = _map_candidate(raw)
        except ValueError as e:
            # Preserve failed candidates even if image_url invalid — use placeholder for audit
            status = raw.get("status") or raw.get("retrieval_status") or raw.get("acquisition_status") or "failed"
            if status == "failed":
                # Inject placeholder image_url to keep failed candidate auditable
                raw_fixed = dict(raw)
                if not raw_fixed.get("image_url"):
                    raw_fixed["image_url"] = "https://example.com/failed-placeholder.jpg"
                # Ensure required fields
                raw_fixed.setdefault("candidate_id", raw.get("candidate_id", f"cand_{len(candidates)+1:03d}"))
                raw_fixed.setdefault("discovery_provider", raw.get("discovery_provider") or raw.get("provider") or "unknown")
                raw_fixed.setdefault("search_rank", raw.get("search_rank", len(candidates)+1))
                raw_fixed["status"] = "failed"
                try:
                    cand = _map_candidate(raw_fixed)
                except ValueError:
                    # If still invalid, skip (should not happen)
                    continue
            else:
                raise
        candidates.append(cand)

    # Sort deterministically before hashing: search_rank asc, candidate_id tie breaker
    candidates.sort(key=lambda c: (c.search_rank, c.candidate_id))

    # Compute candidate evidence_hash for successful candidates only
    for cand in candidates:
        if cand.status == "success":
            # hash_candidate excludes evidence_hash field
            cand.evidence_hash = hash_candidate(cand.to_dict())
        else:
            cand.evidence_hash = None

    # Generate run metadata if not injected (for deterministic tests)
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    if pipeline_run_id is None:
        pipeline_run_id = str(uuid.uuid4())

    # Build envelope without root hash first
    envelope = EvidenceEnvelope(
        envelope_version="1.0",
        query_image=query_image,
        manifest_timestamp=manifest_timestamp,
        created_at=created_at,
        pipeline_run_id=pipeline_run_id,
        candidate_count=candidate_count,
        acquired_count=sum(1 for c in candidates if c.status == "success"),
        evidence_hash=None,
        candidates=candidates,
        timeline=normalized_timeline,
    )

    # Compute root hash: build complete envelope including candidate hashes + timeline, exclude top-level evidence_hash
    root_hash = hash_envelope(envelope.to_dict())
    envelope.evidence_hash = root_hash

    # Append evidence_built event — this MUST be included before final hash per spec
    # To keep spec semantics (envelope includes evidence_built), we need to include it
    # in the hash. So we add it then recompute hash.
    # Order: evidence_built is last event; if timeline already contained it, don't duplicate
    has_evidence_built = any(t.event == "evidence_built" for t in envelope.timeline)
    if not has_evidence_built:
        ev = create_timeline_event(
            "evidence_built",
            detail={"evidence_hash": root_hash, "candidate_count": envelope.candidate_count, "acquired_count": envelope.acquired_count},
            actor="evidence",
            ts=created_at,
        )
        envelope.timeline.append(ev)
        # Recompute hash with evidence_built included
        # Temporarily clear evidence_hash to recompute
        envelope.evidence_hash = None
        envelope.evidence_hash = hash_envelope(envelope.to_dict())

    # Write output files
    if write_files:
        out_dir = Path(output_dir) if output_dir else Path("data/evidence")
        out_dir.mkdir(parents=True, exist_ok=True)

        # Pretty JSON (human readable) — includes evidence_hash
        pretty_path = out_dir / f"evidence_{envelope.pipeline_run_id}.json"
        with open(pretty_path, "w", encoding="utf-8") as f:
            json.dump(envelope.to_dict(), f, indent=2, ensure_ascii=False)
            f.write("\n")

        # Canonical JSON — exact preimage used for root hashing, decoded as UTF-8
        # Per spec: canonical file must be exact bytes used to compute root hash,
        # i.e., envelope WITHOUT evidence_hash field, canonicalized.
        # Document this behavior: canonical file excludes evidence_hash.
        canonical_dict = {k: v for k, v in envelope.to_dict().items() if k != "evidence_hash"}
        canonical_bytes = canonical_dumps(canonical_dict)
        canonical_path = out_dir / f"evidence_{envelope.pipeline_run_id}.canonical.json"
        with open(canonical_path, "wb") as f:
            f.write(canonical_bytes)

    return envelope
