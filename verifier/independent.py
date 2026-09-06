"""Independent offline verifier for evidence.

Verifies evidence file without rerunning search/acquisition and without
depending on search provider internals. Also optionally checks on-chain anchor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from evidence.hash import hash_candidate, hash_envelope
from evidence.canonical import canonical_dumps


def _load_evidence(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"evidence file not found: {path}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("evidence JSON must be object")
    return data


def verify_offline(
    envelope_path: str | Path,
    client: Optional[object] = None,
    anchor_dir: str | Path = "data/blockchain",
) -> dict:
    """Verify evidence file offline.

    Steps:
      1. Load evidence JSON
      2. For each candidate (preserve order): remove evidence_hash, recompute if status==success
      3. Recompute root hash (remove only root evidence_hash, preserve candidate hashes)
      4. Compare, optionally check anchor + on-chain

    Returns structured dict:
      {valid, candidate_hashes_valid, root_hash_valid, stored_hash, recomputed_hash,
       mismatches[], on_chain, anchor}

    Does not modify any files.
    """
    data = _load_evidence(envelope_path)
    stored_hash: Optional[str] = data.get("evidence_hash")
    if not stored_hash:
        return {
            "valid": False,
            "candidate_hashes_valid": False,
            "root_hash_valid": False,
            "stored_hash": stored_hash,
            "recomputed_hash": None,
            "mismatches": [{"type": "missing_root_hash", "detail": "evidence_hash is missing or empty"}],
            "on_chain": None,
            "anchor": None,
        }

    mismatches = []
    candidate_hashes_valid = True

    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        mismatches.append({"type": "invalid_candidates", "detail": "candidates is not a list"})
        candidate_hashes_valid = False
    else:
        for idx, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                mismatches.append({"type": "invalid_candidate", "index": idx, "detail": "candidate is not dict"})
                candidate_hashes_valid = False
                continue
            status = cand.get("status")
            stored_cand_hash = cand.get("evidence_hash")
            # Failed candidates: expected to have None/empty hash and not recomputed
            if status == "failed":
                if stored_cand_hash not in (None, ""):
                    # According spec failed should be None; but if present we still validate?
                    # For Phase 1, failed evidence_hash must be None — treat non-None as mismatch
                    mismatches.append({
                        "type": "failed_candidate_hash_not_none",
                        "candidate_id": cand.get("candidate_id"),
                        "stored": stored_cand_hash,
                    })
                    candidate_hashes_valid = False
                continue
            # Success candidates: must have 64-hex hash, recompute
            if status == "success":
                if not stored_cand_hash or not isinstance(stored_cand_hash, str):
                    mismatches.append({
                        "type": "missing_candidate_hash",
                        "candidate_id": cand.get("candidate_id"),
                        "stored": stored_cand_hash,
                    })
                    candidate_hashes_valid = False
                    continue
                # recompute without evidence_hash
                try:
                    recomputed = hash_candidate(cand)
                except Exception as e:
                    mismatches.append({
                        "type": "candidate_hash_error",
                        "candidate_id": cand.get("candidate_id"),
                        "error": str(e),
                    })
                    candidate_hashes_valid = False
                    continue
                if recomputed.lower() != stored_cand_hash.lower():
                    mismatches.append({
                        "type": "candidate_hash_mismatch",
                        "candidate_id": cand.get("candidate_id"),
                        "stored": stored_cand_hash,
                        "recomputed": recomputed,
                    })
                    candidate_hashes_valid = False
            else:
                # unknown status — treat as candidate hash invalid
                mismatches.append({
                    "type": "unknown_status",
                    "candidate_id": cand.get("candidate_id"),
                    "status": status,
                })
                candidate_hashes_valid = False

    # Recompute root hash: remove only root evidence_hash, preserve candidate hashes
    try:
        # Use hash_envelope helper which removes evidence_hash and canonicalizes
        recomputed_hash = hash_envelope(data)
    except Exception as e:
        return {
            "valid": False,
            "candidate_hashes_valid": candidate_hashes_valid,
            "root_hash_valid": False,
            "stored_hash": stored_hash,
            "recomputed_hash": None,
            "mismatches": mismatches + [{"type": "root_hash_error", "error": str(e)}],
            "on_chain": None,
            "anchor": None,
        }

    root_hash_valid = (recomputed_hash.lower() == stored_hash.lower())
    if not root_hash_valid:
        mismatches.append({
            "type": "root_hash_mismatch",
            "stored": stored_hash,
            "recomputed": recomputed_hash,
        })

    # Anchor discovery (optional, never invalidates offline integrity)
    anchor = None
    anchor_path = Path(anchor_dir) / f"anchor_{stored_hash}.json"
    if anchor_path.exists():
        try:
            with open(anchor_path, "r", encoding="utf-8") as f:
                anchor = json.load(f)
            # Verify anchor evidence_hash matches stored root
            if anchor.get("evidence_hash", "").lower() != stored_hash.lower():
                mismatches.append({
                    "type": "anchor_hash_mismatch",
                    "anchor_hash": anchor.get("evidence_hash"),
                    "stored_hash": stored_hash,
                })
                # anchor mismatch is not hash invalidation but reported
        except Exception as e:
            mismatches.append({"type": "anchor_load_error", "error": str(e)})
            anchor = None

    # On-chain check if client supplied
    on_chain = None
    if client is not None:
        try:
            from blockchain.verification import verify_evidence
            result = verify_evidence(stored_hash, client)  # type: ignore
            on_chain = bool(result.get("found"))
            # If anchor file exists, compare chain data when available
            if anchor is not None and result.get("found"):
                # optional consistency check
                if anchor.get("transaction_hash") and result.get("transaction_hash"):
                    if anchor["transaction_hash"].lower() != result["transaction_hash"].lower():
                        # not fatal for valid, but note mismatch
                        mismatches.append({"type": "anchor_tx_mismatch", "anchor_tx": anchor.get("transaction_hash"), "chain_tx": result.get("transaction_hash")})
        except Exception as e:
            mismatches.append({"type": "on_chain_error", "error": str(e)})
            on_chain = None
    else:
        # If no client but anchor file exists, infer on_chain=None (not checked)
        # If we want to report anchor existence as on_chain hint, keep None per spec (distinguish integrity vs chain)
        pass

    valid = candidate_hashes_valid and root_hash_valid

    # Note: on_chain does NOT affect valid (offline integrity)
    # Tampered evidence must not become valid because old anchor exists
    # So valid is strictly candidate_hashes_valid && root_hash_valid

    return {
        "valid": valid,
        "candidate_hashes_valid": candidate_hashes_valid,
        "root_hash_valid": root_hash_valid,
        "stored_hash": stored_hash,
        "recomputed_hash": recomputed_hash,
        "mismatches": mismatches,
        "on_chain": on_chain,
        "anchor": anchor,
    }
