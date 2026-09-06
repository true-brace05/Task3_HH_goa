#!/usr/bin/env python3
"""End-to-end local blockchain demo (no external chain required by default).

Flow:
  1. Build evidence (mock discovery + stub verification if needed)
  2. Root SHA-256 hash
  3. InMemory (or real if configured) registration → tx/block
  4. Verify original → VALID + ON-CHAIN
  5. Tamper copy → INVALID
  6. Show old anchor not making tampered valid

Usage:
  python scripts/e2e_demo.py
  python scripts/e2e_demo.py --real-chain   # requires CHAIN_RPC_URL + PRIVATE_KEY + CONTRACT_ADDRESS or deploy
"""

import argparse
import json
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.builder import build_evidence
from verifier.independent import verify_offline
from blockchain.client import InMemoryBlockchainClient
from blockchain.registration import register_evidence


FIXTURE_MANIFEST = {
    "query_image": "query.jpg",
    "candidate_count": 2,
    "acquired_count": 2,
    "failed_count": 0,
    "timestamp": "2026-09-06T12:00:00+00:00",
    "candidates": [
        {
            "candidate_id": "cand_001",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_001.jpeg",
            "content_type": "image/jpeg",
            "file_size": 100,
            "content_sha256": "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95",
            "source_url": "https://example.com/page1",
            "image_url": "https://example.com/img1.jpg",
            "thumbnail_url": None,
            "title": None,
            "search_rank": 1,
            "discovery_provider": "yandex-visual-search",
            "verification": {
                "method": "stub-hash-v1",
                "score": "0.900000",
                "decision": "match",
                "timestamp": "2026-09-06T12:00:00+00:00",
                "query_face_detected": True,
                "candidate_face_detected": True,
                "error": None,
            },
        },
        {
            "candidate_id": "cand_002",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_002.jpeg",
            "content_type": "image/jpeg",
            "file_size": 200,
            "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "source_url": "https://example.com/page2",
            "image_url": "https://example.com/img2.jpg",
            "thumbnail_url": None,
            "title": "Second",
            "search_rank": 2,
            "discovery_provider": "yandex-visual-search",
            "verification": {
                "method": "stub-hash-v1",
                "score": "0.200000",
                "decision": "no_match",
                "timestamp": "2026-09-06T12:00:00+00:00",
                "query_face_detected": True,
                "candidate_face_detected": True,
                "error": None,
            },
        },
    ],
}


def main():
    parser = argparse.ArgumentParser(description="E2E local blockchain demo")
    parser.add_argument("--real-chain", action="store_true", help="Use real chain via config")
    args = parser.parse_args()

    print("=== Phase 5 E2E Demo: Evidence → Hash → Blockchain → Verification ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir) / "evidence"
        anchor_dir = Path(tmpdir) / "blockchain"
        evidence_dir.mkdir()
        anchor_dir.mkdir()

        # 1-2. Build evidence
        print("[1] Building evidence ...")
        env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="demo-e2e-0001", output_dir=str(evidence_dir), write_files=True)
        evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
        print(f"    evidence: {evidence_path}")
        print(f"    root hash: {env.evidence_hash}")
        print(f"    candidates: {len(env.candidates)} (hashes: {[c.evidence_hash[:8]+'...' for c in env.candidates]})")
        print(f"    timeline: {[e.event for e in env.timeline]}")

        # 3-5. Register
        print("\n[2] Registering on blockchain ...")
        if args.real_chain:
            from config.settings import get_settings
            from blockchain.client import Web3BlockchainClient

            settings = get_settings()
            client = Web3BlockchainClient(settings.chain_rpc_url, settings.contract_address, settings.private_key, settings.chain_id)
        else:
            client = InMemoryBlockchainClient()
        anchor = register_evidence(env, client, anchor_dir=str(anchor_dir), write_anchor=True)
        print(f"    contract: {anchor['contract_address']}")
        print(f"    tx: {anchor['transaction_hash']}")
        print(f"    block: {anchor['block_number']}")

        # 6-7. Verify original
        print("\n[3] Verifying original (offline + on-chain) ...")
        res = verify_offline(evidence_path, client=client, anchor_dir=str(anchor_dir))
        print(f"    valid: {res['valid']}  candidate_hashes_valid: {res['candidate_hashes_valid']}  root_hash_valid: {res['root_hash_valid']}  on_chain: {res['on_chain']}")
        print(f"    → {'✓ VALID + ON-CHAIN' if res['valid'] and res['on_chain'] else '✗ UNEXPECTED'}")

        # 8-10. Tamper copy
        print("\n[4] Tampering copy (change verification score) ...")
        tampered_path = Path(tmpdir) / "tampered.json"
        data = json.loads(evidence_path.read_text())
        data["candidates"][0]["verification"]["score"] = "0.100000"
        # Keep stored hash unchanged to simulate tampering without re-hashing
        tampered_path.write_text(json.dumps(data, indent=2))
        res2 = verify_offline(tampered_path, client=client, anchor_dir=str(anchor_dir))
        print(f"    valid: {res2['valid']}  root_hash_valid: {res2['root_hash_valid']}  on_chain: {res2['on_chain']}")
        print(f"    mismatches: {res2['mismatches'][:1]}")
        print(f"    → {'✓ TAMPER DETECTED (invalid)' if not res2['valid'] else '✗ FAILED to detect'}")
        print(f"    on_chain for tampered (still anchor exists for original): {res2['on_chain']} — but valid is false, old anchor does not make valid")

        print("\n=== Demo complete ===")
        print("Evidence immutability: verification tampering → candidate hash mismatch → root mismatch → valid=false")
        print("Blockchain: InMemory anchor separate from evidence; real chain uses same flow via --real-chain")


if __name__ == "__main__":
    main()
