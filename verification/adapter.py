"""Face verification adapter — thin adapter over real face module.

Ownership: Member 1 (face recognition). Member 3 (evidence/blockchain) treats
this as upstream input and never decides the model.

Current implementation: REAL face verification using InsightFace buffalo_l
(face.detector + face.embedder + face.matcher + face.ranking). Replaces
stub-hash-v1 (deterministic hash) with cosine similarity on L2-normalized
embeddings. Evidence hashing remains identical — only VerificationData
production changes.

Evidence remains model-agnostic: it records VerificationData{method,score,decision}
and hashes deterministic string score.

Adapter contract:
  verify_candidate(query_image, candidate_image) -> VerificationData
  verify_candidate_with_embedding(reference_embedding, candidate_image) -> VerificationData
  get_reference_embedding(query_image) -> np.ndarray (cached per pipeline run via pipeline reuse)

Score is always deterministic 6-decimal string via format_score, never float,
so evidence canonical hashing never sees floats.
Decision is lowercase evidence vocab: match | no_match | inconclusive | error
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np

from evidence.schema import VerificationData

logger = logging.getLogger(__name__)

METHOD = "insightface-buffalo_l"
DEFAULT_HIGH_THRESHOLD = 0.70
DEFAULT_LOW_THRESHOLD = 0.40
# Backward compat single threshold (not used for ranking, but kept for API compat)
DEFAULT_THRESHOLD = 0.60
SCORE_PRECISION = 6


def format_score(value: float) -> str:
    """Deterministic decimal string with fixed precision."""
    return f"{float(value):.{SCORE_PRECISION}f}"


# Local import helpers to allow mocking in tests and graceful failure if face deps missing
def _get_face_modules():
    """Import face modules lazily (allows unittest.mock.patch on face.*)."""
    from face.detector import detect_query_face  # type: ignore
    from face.embedder import generate_embedding  # type: ignore
    from face.matcher import verify_candidate as face_verify_candidate  # type: ignore
    from face.ranking import make_decision  # type: ignore

    return detect_query_face, generate_embedding, face_verify_candidate, make_decision


def get_reference_embedding(query_image: str | Path):
    """Detect query face (exactly 1) and return normalized embedding.

    Raises:
        FileNotFoundError, ValueError (no face / multiple faces), etc.
    Returns:
        (embedding: np.ndarray, face_info: dict)
    """
    detect_query_face, generate_embedding, _, _ = _get_face_modules()
    face_info = detect_query_face(query_image)
    embedding = generate_embedding(face_info)
    return embedding, face_info


def _map_decision(face_status: str, best_similarity: Optional[float],
                  high_threshold: float = DEFAULT_HIGH_THRESHOLD,
                  low_threshold: float = DEFAULT_LOW_THRESHOLD) -> str:
    """Map face matcher result to evidence lowercase decision."""
    if face_status == "error":
        return "error"
    if face_status == "no_face":
        return "inconclusive"
    # success -> use ranking thresholds
    try:
        from face.ranking import make_decision as face_make_decision
        raw = face_make_decision(best_similarity, high_threshold=high_threshold, low_threshold=low_threshold)
    except Exception:
        # fallback three-state when face.ranking not importable (e.g., insightface missing)
        if best_similarity is None:
            return "inconclusive"
        sim = float(best_similarity)
        if sim >= high_threshold:
            return "match"
        if sim <= low_threshold:
            return "no_match"
        return "inconclusive"
    # face returns uppercase "MATCH"/"NO MATCH"/"INCONCLUSIVE"
    return raw.lower().replace(" ", "_")


def verify_candidate_with_embedding(
    reference_embedding: np.ndarray,
    candidate_image: str | Path,
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
    method: str = METHOD,
    query_face_detected: Optional[bool] = True,
) -> VerificationData:
    """Verify candidate using precomputed reference embedding (reuse per pipeline run)."""
    ts = datetime.now(timezone.utc).isoformat()
    cand_path = str(candidate_image)
    path = Path(cand_path)

    if not path.exists() or not path.is_file():
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=query_face_detected,
            candidate_face_detected=None,
            error=f"candidate image not found: {cand_path}",
        )

    # Validate readable image via Pillow (keeps evidence pipeline robust)
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            img.verify()
    except Exception as e:
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=query_face_detected,
            candidate_face_detected=None,
            error=f"corrupted/unreadable candidate image: {e}",
        )

    # Delegate to real face matcher
    try:
        _, _, face_verify_candidate, _ = _get_face_modules()
        result = face_verify_candidate(reference_embedding, cand_path)
    except Exception as e:
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=query_face_detected,
            candidate_face_detected=None,
            error=f"face verification failed: {e}",
        )

    status = result.get("status", "error")
    best_sim = result.get("best_similarity")
    faces_detected = result.get("faces_detected", 0)
    error = result.get("error")

    # candidate_face_detected: True if >=1 face, False if 0, None if error
    if status == "error":
        cand_detected = None
    else:
        cand_detected = bool(faces_detected > 0)

    if status == "no_face":
        return VerificationData(
            method=method,
            score=None,
            decision="inconclusive",
            timestamp=ts,
            query_face_detected=query_face_detected,
            candidate_face_detected=False,
            error=error,
        )
    if status == "error":
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=query_face_detected,
            candidate_face_detected=cand_detected,
            error=error,
        )

    # success
    try:
        score_str = format_score(float(best_sim)) if best_sim is not None else None
    except Exception:
        score_str = None

    decision = _map_decision(status, best_sim, high_threshold, low_threshold)

    return VerificationData(
        method=method,
        score=score_str,
        decision=decision,
        timestamp=ts,
        query_face_detected=query_face_detected,
        candidate_face_detected=cand_detected,
        error=None,
    )


def verify_candidate(
    query_image: str | Path,
    candidate_image: str | Path,
    threshold: float = DEFAULT_THRESHOLD,
    method: str = METHOD,
    high_threshold: Optional[float] = None,
    low_threshold: Optional[float] = None,
) -> VerificationData:
    """Verify single candidate against query (standalone, recomputes query embedding).

    For pipeline efficiency, prefer verify_candidate_with_embedding with cached
    reference embedding (see pipeline._run_face_verification). This function
    remains for backward compatibility and is used by standalone tests.

    Args:
        query_image: path to query image (must contain exactly 1 face)
        candidate_image: path to candidate image
        threshold: legacy single threshold; if high/low not provided, maps to high=threshold
        method: evidence method string
        high_threshold, low_threshold: ranking thresholds (default 0.70/0.40)

    Returns:
        VerificationData with deterministic 6-decimal string score.
    """
    # Resolve thresholds: if legacy threshold provided without high/low, use it as high, low = high-0.30
    if high_threshold is None and low_threshold is None and threshold != DEFAULT_THRESHOLD:
        # caller passed custom single threshold -> honor it as high, derive low
        high_threshold = float(threshold)
        low_threshold = max(0.0, float(threshold) - 0.30)
    if high_threshold is None:
        high_threshold = DEFAULT_HIGH_THRESHOLD
    if low_threshold is None:
        low_threshold = DEFAULT_LOW_THRESHOLD

    ts = datetime.now(timezone.utc).isoformat()
    query_path = str(query_image)
    cand_path = str(candidate_image)

    # Validate files exist (query first)
    for p, label in [(query_path, "query"), (cand_path, "candidate")]:
        path = Path(p)
        if not path.exists() or not path.is_file():
            return VerificationData(
                method=method,
                score=None,
                decision="error",
                timestamp=ts,
                query_face_detected=None,
                candidate_face_detected=None,
                error=f"{label} image not found: {p}",
            )

    # Validate images readable
    try:
        from PIL import Image  # type: ignore
        for p in [query_path, cand_path]:
            with Image.open(p) as img:
                img.verify()
    except Exception as e:
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=None,
            candidate_face_detected=None,
            error=f"corrupted/unreadable image: {e}",
        )

    # Generate query embedding (exactly 1 face required)
    try:
        reference_embedding, _ = get_reference_embedding(query_path)
        query_detected = True
    except Exception as e:
        # No face or multiple faces in query -> error per face spec, but evidence decision = error/inconclusive
        # Detect if no face vs multiple
        msg = str(e).lower()
        if "no face" in msg or "no face detected" in msg:
            return VerificationData(
                method=method,
                score=None,
                decision="inconclusive",
                timestamp=ts,
                query_face_detected=False,
                candidate_face_detected=None,
                error=str(e),
            )
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=None,
            candidate_face_detected=None,
            error=str(e),
        )

    # Delegate with cached embedding
    return verify_candidate_with_embedding(
        reference_embedding,
        cand_path,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
        method=method,
        query_face_detected=query_detected,
    )


def verify_candidates(
    query_image: str | Path,
    candidate_paths: List[str | Path] | Dict[str, str | Path],
    threshold: float = DEFAULT_THRESHOLD,
    high_threshold: Optional[float] = None,
    low_threshold: Optional[float] = None,
) -> Dict[str, VerificationData]:
    """Batch verification with single query embedding reuse.

    Accepts list of paths or dict candidate_id->path.
    Never crashes on single candidate failure.
    """
    # Resolve thresholds
    if high_threshold is None and low_threshold is None and threshold != DEFAULT_THRESHOLD:
        high_threshold = float(threshold)
        low_threshold = max(0.0, float(threshold) - 0.30)
    if high_threshold is None:
        high_threshold = DEFAULT_HIGH_THRESHOLD
    if low_threshold is None:
        low_threshold = DEFAULT_LOW_THRESHOLD

    results: Dict[str, VerificationData] = {}

    # Try to get query embedding once
    try:
        reference_embedding, _ = get_reference_embedding(str(query_image))
        query_detected = True
        query_error = None
    except Exception as e:
        # Query failed -> all candidates get error/inconclusive
        msg = str(e).lower()
        is_no_face = "no face" in msg
        for idx, cpath in enumerate(candidate_paths if isinstance(candidate_paths, dict) else candidate_paths):  # type: ignore
            if isinstance(candidate_paths, dict):
                cid = str(idx) if not isinstance(idx, str) else str(idx)
                # dict iteration handled below
                break
            else:
                cid = f"cand_{idx+1:03d}"
                if isinstance(cpath, dict):
                    cid = cpath.get("candidate_id", cid)
            results[str(cid)] = VerificationData(
                method=METHOD,
                score=None,
                decision="inconclusive" if is_no_face else "error",
                timestamp=datetime.now(timezone.utc).isoformat(),
                query_face_detected=False if is_no_face else None,
                candidate_face_detected=None,
                error=str(e),
            )
        # For dict input, need proper handling
        if isinstance(candidate_paths, dict):
            results.clear()
            for cid, cpath in candidate_paths.items():
                results[str(cid)] = VerificationData(
                    method=METHOD,
                    score=None,
                    decision="inconclusive" if is_no_face else "error",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    query_face_detected=False if is_no_face else None,
                    candidate_face_detected=None,
                    error=str(e),
                )
        return results

    if isinstance(candidate_paths, dict):
        for cid, cpath in candidate_paths.items():
            try:
                results[str(cid)] = verify_candidate_with_embedding(
                    reference_embedding, cpath, high_threshold=high_threshold, low_threshold=low_threshold
                )
            except Exception as e:
                results[str(cid)] = VerificationData(
                    method=METHOD, score=None, decision="error",
                    timestamp=datetime.now(timezone.utc).isoformat(), error=str(e)
                )
    else:
        for idx, cpath in enumerate(candidate_paths):
            cid = f"cand_{idx+1:03d}"
            if isinstance(cpath, dict):
                cid = cpath.get("candidate_id", cid)
                cpath = cpath.get("local_path") or cpath.get("image_url") or ""
            try:
                results[str(cid)] = verify_candidate_with_embedding(
                    reference_embedding, cpath, high_threshold=high_threshold, low_threshold=low_threshold
                )
            except Exception as e:
                results[str(cid)] = VerificationData(
                    method=METHOD, score=None, decision="error",
                    timestamp=datetime.now(timezone.utc).isoformat(), error=str(e)
                )
    return results
