"""Registration layer — anchor evidence root hash on chain.

Critical rule: anchor metadata is NEVER written back into the EvidenceEnvelope
hash preimage. Evidence hash is immutable; anchor is stored separately.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Union

from evidence.schema import EvidenceEnvelope
from blockchain.client import BlockchainClient


SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_envelope(envelope: Union[EvidenceEnvelope, dict]) -> EvidenceEnvelope:
    if isinstance(envelope, dict):
        envelope = EvidenceEnvelope.from_dict(envelope)
    if not isinstance(envelope, EvidenceEnvelope):
        raise TypeError(f"envelope must be EvidenceEnvelope or dict, got {type(envelope).__name__}")
    if not envelope.evidence_hash or not SHA256_RE.match(envelope.evidence_hash):
        raise ValueError(f"envelope must have valid lowercase 64-hex evidence_hash, got: {envelope.evidence_hash!r}")
    # ensure lowercase
    envelope.evidence_hash = envelope.evidence_hash.lower()
    return envelope


def register_evidence(
    envelope: Union[EvidenceEnvelope, dict],
    client: BlockchainClient,
    manifest_uri: str = "",
    anchor_dir: Union[str, Path] = "data/blockchain",
    write_anchor: bool = True,
) -> dict:
    """Register envelope root hash via client.

    Returns anchor metadata dict (transaction_hash, block_number, contract_address, evidence_hash, timestamp, manifest_uri).
    Does NOT modify envelope.evidence_hash.
    Writes data/blockchain/anchor_<hash>.json separately.
    """
    env = _validate_envelope(envelope)
    h = env.evidence_hash  # type: ignore

    original_hash = h
    anchor = client.register(h, manifest_uri=manifest_uri)

    # invariant: envelope hash unchanged
    if env.evidence_hash != original_hash:
        raise RuntimeError("envelope hash was modified during registration")

    # anchor must contain required fields
    if anchor.get("evidence_hash", "").lower() != h.lower():
        raise RuntimeError("anchor evidence_hash mismatch")

    # Ensure anchor has all expected keys for downstream verification
    anchor.setdefault("manifest_uri", manifest_uri)
    anchor.setdefault("timestamp", int(time.time()))
    anchor.setdefault("contract_address", client.get_contract_address())

    if write_anchor:
        out_dir = Path(anchor_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        anchor_path = out_dir / f"anchor_{h}.json"
        # Never write private key; anchor contains only public metadata
        with open(anchor_path, "w", encoding="utf-8") as f:
            json.dump(anchor, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return dict(anchor)
