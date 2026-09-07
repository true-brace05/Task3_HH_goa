"""Verification layer — check if evidence hash is anchored."""

from __future__ import annotations

import re
from typing import Optional

from blockchain.client import BlockchainClient


SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_hash(evidence_hash: str) -> str:
    if not isinstance(evidence_hash, str):
        raise ValueError(f"evidence_hash must be str, got {type(evidence_hash).__name__}")
    if not SHA256_RE.match(evidence_hash):
        raise ValueError(f"evidence_hash must be 64 hex chars, got: {evidence_hash!r}")
    return evidence_hash.lower()


def verify_evidence(evidence_hash: str, client: BlockchainClient) -> dict:
    """Verify evidence_hash exists on chain.

    Returns structured dict:
      {found: bool, evidence_hash: str, submitter: str|None, timestamp: int|None,
       contract_address: str, transaction_hash: str|None, block_number: int|None, manifest_uri: str|None}
    """
    h = _validate_hash(evidence_hash)
    result = client.verify(h)
    if result is None:
        return {
            "found": False,
            "evidence_hash": h,
            "submitter": None,
            "timestamp": None,
            "contract_address": client.get_contract_address(),
            "transaction_hash": None,
            "block_number": None,
            "manifest_uri": None,
        }
    return {
        "found": True,
        "evidence_hash": h,
        "submitter": result.get("submitter"),
        "timestamp": result.get("timestamp"),
        "contract_address": result.get("contract_address", client.get_contract_address()),
        "transaction_hash": result.get("transaction_hash"),
        "block_number": result.get("block_number"),
        "manifest_uri": result.get("manifest_uri"),
    }


def is_verified(evidence_hash: str, client: BlockchainClient) -> bool:
    return verify_evidence(evidence_hash, client)["found"]
