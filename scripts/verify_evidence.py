#!/usr/bin/env python3
"""Verify evidence file (offline + optional on-chain).

Usage:
  python scripts/verify_evidence.py data/evidence/evidence_<id>.json
  python scripts/verify_evidence.py data/evidence/evidence_<id>.json --on-chain
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root on path when run as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from verifier.independent import verify_offline
from blockchain.client import InMemoryBlockchainClient


def main():
    parser = argparse.ArgumentParser(description="Verify evidence integrity")
    parser.add_argument("evidence_path", help="Path to evidence JSON")
    parser.add_argument("--on-chain", action="store_true", help="Verify on-chain via configured client")
    parser.add_argument("--anchor-dir", default="data/blockchain", help="Anchor dir")
    args = parser.parse_args()

    client = None
    if args.on_chain:
        # Try to use configured client, else InMemory
        try:
            from config.settings import get_settings

            settings = get_settings()
            if settings.chain_rpc_url and settings.private_key:
                from blockchain.client import Web3BlockchainClient

                client = Web3BlockchainClient(
                    rpc_url=settings.chain_rpc_url,
                    contract_address=settings.contract_address,
                    private_key=settings.private_key,
                    chain_id=settings.chain_id,
                )
            else:
                client = InMemoryBlockchainClient(contract_address=settings.contract_address or "0x0000000000000000000000000000000000000000")
                # Try to load anchors from disk into client
                anchor_dir = Path(args.anchor_dir)
                if anchor_dir.exists():
                    for p in anchor_dir.glob("anchor_*.json"):
                        try:
                            data = json.loads(p.read_text())
                            h = data.get("evidence_hash")
                            if h:
                                client._store[h.lower()] = data  # type: ignore
                        except Exception:
                            pass
        except Exception as e:
            print(f"WARN: on-chain client not configured: {e}", file=sys.stderr)
            client = None

    result = verify_offline(args.evidence_path, client=client, anchor_dir=args.anchor_dir)
    print(json.dumps(result, indent=2))
    if result["valid"]:
        print("\n✓ VALID" + (" + ON-CHAIN" if result.get("on_chain") else " (offline)"))
    else:
        print("\n✗ INVALID — mismatches:")
        for m in result["mismatches"]:
            print(" ", m)
        if result.get("on_chain") is False:
            print("  on_chain: false (anchor not found or hash not anchored)")
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
