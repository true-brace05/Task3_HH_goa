"""SHA-256 hashing for evidence.

Candidate hashing:
  1. Convert model/object to plain dict.
  2. Remove evidence_hash.
  3. Canonicalize.
  4. SHA-256 -> lowercase hex.

Envelope hashing:
  1. Convert envelope to plain dict.
  2. Remove top-level evidence_hash (preserve candidate hashes).
  3. Canonicalize complete envelope.
  4. SHA-256 -> lowercase hex.

Does NOT recompute content_sha256.
"""

from __future__ import annotations

import hashlib
from typing import Any

from evidence.canonical import canonical_dumps


def sha256_hex(data: bytes) -> str:
    """Return lowercase hex SHA-256 of data."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"sha256_hex expects bytes, got {type(data).__name__}")
    return hashlib.sha256(data).hexdigest()


def _to_dict(obj: Any) -> dict:
    """Convert object to plain dict."""
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"Cannot convert {type(obj).__name__} to dict")


def hash_candidate(candidate_data: Any) -> str:
    """Hash a single candidate evidence dict/object.

    Excludes evidence_hash field before hashing.
    """
    d = _to_dict(candidate_data)
    # Remove evidence_hash key if present
    d = {k: v for k, v in d.items() if k != "evidence_hash"}
    data = canonical_dumps(d)
    return sha256_hex(data)


def hash_envelope(envelope_data: Any) -> str:
    """Hash complete evidence envelope.

    Excludes top-level evidence_hash only; preserves candidate hashes.
    """
    d = _to_dict(envelope_data)
    d = {k: v for k, v in d.items() if k != "evidence_hash"}
    data = canonical_dumps(d)
    return sha256_hex(data)
