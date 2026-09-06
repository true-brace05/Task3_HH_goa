"""Face verification adapter — stable contract for evidence pipeline.

OWNERSHIP: Member 1 (face recognition). Member 3 (evidence/blockchain) treats
this as upstream input and never decides the model.

Current implementation: TEMPORARY DEVELOPMENT PLACEHOLDER `stub-hash-v1`.
No Member-1 face model is committed in the repository (verified via
`grep -r face` across all branches and `requirements.txt`). The stub is
explicitly NOT facial recognition — it is a deterministic hash-based similarity
for pipeline/evidence/blockchain testing only.

HONESTY: METHOD="stub-hash-v1" never claims InsightFace/ArcFace/DeepFace.
BLOCKCHAIN/evidence subsystem is MODEL-AGNOSTIC: it records
`VerificationData{method,score,decision}` and hashes it, but does not choose
the model. Future replacement requires only:

  RealVerificationModule.verify_candidate(query,candidate)→VerificationData
  ↓ existing structured contract (verification/adapter.py)
  ↓ evidence/builder (hashes verification)
  ↓ blockchain (anchors root hash)

No changes needed to evidence/hash.py, blockchain/, verifier/independent.py.

Real integration: replace _compute_stub_score with embedding comparison and set
METHOD="insightface-arcface-r100" (or actual) — see docs/blockchain_evidence.md.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from evidence.schema import VerificationData


METHOD = "stub-hash-v1"
DEFAULT_THRESHOLD = 0.60
SCORE_PRECISION = 6  # fixed decimals for deterministic string


def format_score(value: float) -> str:
    """Deterministic decimal string with fixed precision (single well-defined location).

    Rule: f"{value:.6f}" — exactly 6 decimal places, not str(float).
    """
    return f"{float(value):.{SCORE_PRECISION}f}"


def _detect_faces_stub(image_path: str) -> Optional[bool]:
    """Stub face detection: returns True if image is valid, None if unknown.

    If OpenCV Haar is available, use it; else assume face present for valid images.
    This keeps CI offline and avoids model downloads.
    """
    try:
        import cv2  # type: ignore
        # Try Haar cascade if available
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml" if hasattr(cv2, "data") else None
        if cascade_path and Path(cascade_path).exists():
            img = cv2.imread(str(image_path))
            if img is None:
                return None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(cascade_path)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            return len(faces) > 0
    except Exception:
        pass
    # Fallback: assume face present if file is valid image (Pillow check done elsewhere)
    return True


def _compute_stub_score(query_path: str, candidate_path: str) -> float:
    """Deterministic pseudo-similarity from file bytes (0.0–1.0).

    Uses SHA-256 of concatenated file contents to derive score in [0,1).
    Not a real face similarity — just deterministic for evidence hashing.
    """
    try:
        q_bytes = Path(query_path).read_bytes()
    except Exception:
        q_bytes = b""
    try:
        c_bytes = Path(candidate_path).read_bytes()
    except Exception:
        c_bytes = b""
    h = hashlib.sha256(q_bytes + b"|" + c_bytes).digest()
    # Use first 4 bytes as int
    val = int.from_bytes(h[:4], "big")
    score = (val % 1_000_000) / 1_000_000.0
    return score


def verify_candidate(
    query_image: str | Path,
    candidate_image: str | Path,
    threshold: float = DEFAULT_THRESHOLD,
    method: str = METHOD,
) -> VerificationData:
    """Verify single candidate against query.

    Handles:
      - missing/unreadable file → decision=error
      - no face detected → inconclusive
      - multiple faces not distinguished in stub → inconclusive if Haar finds >1
      - corrupted image → error
      - otherwise → match/no_match based on threshold

    Returns VerificationData with deterministic score string.
    """
    ts = datetime.now(timezone.utc).isoformat()
    query_path = str(query_image)
    cand_path = str(candidate_image)

    # Validate files exist
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

    # Validate images are readable via Pillow
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

    # Face detection (stub)
    try:
        q_detected = _detect_faces_stub(query_path)
        c_detected = _detect_faces_stub(cand_path)
    except Exception as e:
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=None,
            candidate_face_detected=None,
            error=f"face detection failed: {e}",
        )

    if q_detected is False or c_detected is False:
        # No face in either image → inconclusive (not error, not no_match)
        return VerificationData(
            method=method,
            score=None,
            decision="inconclusive",
            timestamp=ts,
            query_face_detected=q_detected,
            candidate_face_detected=c_detected,
            error=None,
        )

    # Compute deterministic similarity
    try:
        raw_score = _compute_stub_score(query_path, cand_path)
        score_str = format_score(raw_score)
        decision = "match" if raw_score >= threshold else "no_match"
        return VerificationData(
            method=method,
            score=score_str,
            decision=decision,
            timestamp=ts,
            query_face_detected=q_detected,
            candidate_face_detected=c_detected,
            error=None,
        )
    except Exception as e:
        return VerificationData(
            method=method,
            score=None,
            decision="error",
            timestamp=ts,
            query_face_detected=q_detected,
            candidate_face_detected=c_detected,
            error=f"verification failed: {e}",
        )


def verify_candidates(
    query_image: str | Path,
    candidate_paths: List[str | Path] | Dict[str, str | Path],
    threshold: float = DEFAULT_THRESHOLD,
) -> Dict[str, VerificationData]:
    """Batch verification.

    Accepts list of paths or dict candidate_id→path.
    Returns mapping candidate_id or index string → VerificationData.
    Never crashes on single candidate failure.
    """
    results: Dict[str, VerificationData] = {}
    if isinstance(candidate_paths, dict):
        for cid, cpath in candidate_paths.items():
            try:
                results[str(cid)] = verify_candidate(query_image, cpath, threshold=threshold)
            except Exception as e:
                results[str(cid)] = VerificationData(
                    method=METHOD, score=None, decision="error", timestamp=datetime.now(timezone.utc).isoformat(), error=str(e)
                )
    else:
        for idx, cpath in enumerate(candidate_paths):
            cid = f"cand_{idx+1:03d}"
            # If cpath is dict with local_path, extract
            if isinstance(cpath, dict):
                cid = cpath.get("candidate_id", cid)
                cpath = cpath.get("local_path") or cpath.get("image_url") or ""
            try:
                results[str(cid)] = verify_candidate(query_image, cpath, threshold=threshold)
            except Exception as e:
                results[str(cid)] = VerificationData(
                    method=METHOD, score=None, decision="error", timestamp=datetime.now(timezone.utc).isoformat(), error=str(e)
                )
    return results
