"""Phase 5 hardening — deployment, Web3, immutability, tampering."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.builder import build_evidence
from verifier.independent import verify_offline
from blockchain.client import InMemoryBlockchainClient, hash_to_bytes32, load_artifact_abi
from blockchain.registration import register_evidence
from blockchain.verification import verify_evidence


FIXTURE_MANIFEST = {
    "query_image": "query.jpg",
    "candidate_count": 1,
    "acquired_count": 1,
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
            "content_sha256": "a" * 64,
            "source_url": "https://example.com/p",
            "image_url": "https://example.com/img.jpg",
            "thumbnail_url": None,
            "title": None,
            "search_rank": 1,
            "discovery_provider": "yandex-visual-search",
            "verification": {"method": "stub-hash-v1", "score": "0.800000", "decision": "match", "timestamp": "2026-09-06T12:00:00+00:00", "query_face_detected": True, "candidate_face_detected": True, "error": None},
        }
    ],
}


class TestArtifactLoading(unittest.TestCase):
    def test_load_abi_exists(self):
        abi = load_artifact_abi()
        self.assertIsNotNone(abi)
        self.assertTrue(any(x.get("name") == "register" for x in abi))

    def test_load_abi_missing(self):
        abi = load_artifact_abi("nonexistent.json")
        self.assertIsNone(abi)


class TestWeb3ConfigGuards(unittest.TestCase):
    def test_missing_rpc(self):
        from blockchain.client import Web3BlockchainClient
        with self.assertRaises((ValueError, ImportError, ConnectionError)):
            Web3BlockchainClient(rpc_url="", contract_address="0x" + "0"*40, private_key="0x" + "a"*64)

    def test_missing_private_key(self):
        from blockchain.client import Web3BlockchainClient
        with self.assertRaises((ValueError, ImportError)):
            Web3BlockchainClient(rpc_url="http://127.0.0.1:8545", contract_address="0x" + "0"*40, private_key="")

    def test_invalid_rpc(self):
        from blockchain.client import Web3BlockchainClient
        try:
            import web3  # noqa
        except ImportError:
            self.skipTest("web3 not installed")
        with self.assertRaises(ConnectionError):
            Web3BlockchainClient(rpc_url="http://127.0.0.1:65530", contract_address="0x" + "0"*40, private_key="0x" + "a"*64)

    def test_hash_to_bytes32_valid(self):
        h = "ab" * 32
        b = hash_to_bytes32(h)
        self.assertEqual(len(b), 32)

    def test_hash_to_bytes32_invalid(self):
        with self.assertRaises(ValueError):
            hash_to_bytes32("short")


class TestImmutabilityRegression(unittest.TestCase):
    def test_evidence_unchanged_after_registration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="immut-0001", output_dir=str(evidence_dir), write_files=True)
            evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
            original_bytes = evidence_path.read_bytes()
            original_hash = env.evidence_hash
            client = InMemoryBlockchainClient()
            anchor = register_evidence(env, client, anchor_dir=str(anchor_dir), write_anchor=True)
            # hash unchanged
            self.assertEqual(env.evidence_hash, original_hash)
            # file unchanged
            self.assertEqual(evidence_path.read_bytes(), original_bytes)
            # anchor separate
            anchor_path = anchor_dir / f"anchor_{original_hash}.json"
            self.assertTrue(anchor_path.exists())
            anchor_data = json.loads(anchor_path.read_text())
            self.assertEqual(anchor_data["evidence_hash"], original_hash)
            self.assertIn("transaction_hash", anchor_data)
            # evidence file does not contain blockchain fields
            ev_data = json.loads(evidence_path.read_text())
            self.assertNotIn("transaction_hash", json.dumps(ev_data))
            self.assertNotIn("block_number", json.dumps(ev_data))


class TestTamperingRegression(unittest.TestCase):
    def _build_and_tamper(self, modify_fn):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="tamper-0001", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            modify_fn(data)
            tampered = Path(tmpdir) / "tampered.json"
            tampered.write_text(json.dumps(data, indent=2))
            result = verify_offline(tampered)
            return result

    def test_candidate_metadata_tampered(self):
        def mod(data):
            data["candidates"][0]["source_url"] = "https://example.com/tampered"
        res = self._build_and_tamper(mod)
        self.assertFalse(res["valid"])
        self.assertFalse(res["root_hash_valid"])

    def test_verification_score_tampered(self):
        def mod(data):
            data["candidates"][0]["verification"]["score"] = "0.100000"
        res = self._build_and_tamper(mod)
        self.assertFalse(res["valid"])
        self.assertTrue(any(m["type"] == "candidate_hash_mismatch" for m in res["mismatches"]))

    def test_verification_decision_tampered(self):
        def mod(data):
            data["candidates"][0]["verification"]["decision"] = "no_match"
        res = self._build_and_tamper(mod)
        self.assertFalse(res["valid"])

    def test_timeline_tampered(self):
        def mod(data):
            if data["timeline"]:
                data["timeline"][0]["detail"]["candidate_count"] = 999
        res = self._build_and_tamper(mod)
        self.assertFalse(res["valid"])
        self.assertFalse(res["root_hash_valid"])

    def test_root_hash_tampered(self):
        def mod(data):
            data["evidence_hash"] = "0" * 64
        res = self._build_and_tamper(mod)
        self.assertFalse(res["valid"])
        self.assertFalse(res["root_hash_valid"])


class TestFullLocalIntegration(unittest.TestCase):
    def test_inmemory_full_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="full-0001", output_dir=str(evidence_dir), write_files=True)
            evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
            client = InMemoryBlockchainClient()
            anchor = register_evidence(env, client, anchor_dir=str(anchor_dir), write_anchor=True)
            # verify via independent verifier
            res = verify_offline(evidence_path, client=client, anchor_dir=str(anchor_dir))
            self.assertTrue(res["valid"])
            self.assertTrue(res["on_chain"])
            # verify via blockchain verification layer
            res2 = verify_evidence(env.evidence_hash, client)
            self.assertTrue(res2["found"])


if __name__ == "__main__":
    unittest.main()
