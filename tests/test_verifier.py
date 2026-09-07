"""Phase 3 verifier tests — tamper detection (6 cases)."""

import json
import tempfile
import unittest
from pathlib import Path
import sys

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
        },
    ],
}


class TestVerifierCases(unittest.TestCase):
    def test_case1_original_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            result = verify_offline(evidence_path)
            self.assertTrue(result["valid"])
            self.assertTrue(result["candidate_hashes_valid"])
            self.assertTrue(result["root_hash_valid"])
            self.assertEqual(result["stored_hash"], env.evidence_hash)
            self.assertEqual(result["recomputed_hash"], env.evidence_hash)
            self.assertEqual(result["mismatches"], [])
            self.assertIsNone(result["on_chain"])

    def test_case2_candidate_field_modified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            data["candidates"][0]["source_url"] = "https://example.com/tampered"
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])
            self.assertFalse(result["candidate_hashes_valid"])
            self.assertFalse(result["root_hash_valid"])
            self.assertTrue(any(m["type"] == "candidate_hash_mismatch" for m in result["mismatches"]))

    def test_case3_timeline_modified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="cccccccc-cccc-cccc-cccc-cccccccccccc", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            # Modify pre-registration timeline detail
            if data["timeline"]:
                data["timeline"][0]["detail"]["candidate_count"] = 999
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])
            self.assertFalse(result["root_hash_valid"])
            # candidate hashes may remain valid but root fails
            self.assertTrue(any(m["type"] == "root_hash_mismatch" for m in result["mismatches"]))

    def test_case4_root_hash_modified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="dddddddd-dddd-dddd-dddd-dddddddddddd", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            data["evidence_hash"] = "0" * 64
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])
            self.assertFalse(result["root_hash_valid"])
            # candidate hashes may still be valid
            self.assertTrue(result["candidate_hashes_valid"])

    def test_case5_anchor_exists_registered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", output_dir=str(evidence_dir), write_files=True)
            evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
            client = InMemoryBlockchainClient()
            register_evidence(env, client, anchor_dir=str(anchor_dir), write_anchor=True)
            result = verify_offline(evidence_path, client=client, anchor_dir=str(anchor_dir))
            self.assertTrue(result["valid"])
            self.assertTrue(result["on_chain"])
            self.assertIsNotNone(result["anchor"])
            self.assertEqual(result["anchor"]["evidence_hash"], env.evidence_hash)

    def test_case6_tampered_with_old_anchor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="ffffffff-ffff-ffff-ffff-ffffffffffff", output_dir=str(evidence_dir), write_files=True)
            evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
            client = InMemoryBlockchainClient()
            register_evidence(env, client, anchor_dir=str(anchor_dir), write_anchor=True)
            # Tamper evidence after anchor
            data = json.loads(evidence_path.read_text())
            data["candidates"][0]["title"] = "tampered"
            # Note: keep stored_hash unchanged, but candidate hash will mismatch and root will mismatch
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path, client=client, anchor_dir=str(anchor_dir))
            self.assertFalse(result["valid"])
            self.assertFalse(result["root_hash_valid"])
            # on_chain should be true for stored_hash (anchor exists) but valid is false
            self.assertTrue(result["on_chain"])
            # mismatches explain tampering
            self.assertTrue(len(result["mismatches"]) > 0)

    def test_missing_anchor_offline_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="11111111-1111-1111-1111-111111111111", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            # No anchor file, no client
            result = verify_offline(evidence_path, anchor_dir=Path(tmpdir) / "no_anchor_dir")
            self.assertTrue(result["valid"])
            self.assertIsNone(result["on_chain"])
            self.assertIsNone(result["anchor"])

    def test_unknown_hash_on_chain_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="22222222-2222-2222-2222-222222222222", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            client = InMemoryBlockchainClient()
            # No registration
            result = verify_offline(evidence_path, client=client, anchor_dir=Path(tmpdir) / "empty_anchor")
            self.assertTrue(result["valid"])  # offline integrity still true
            self.assertFalse(result["on_chain"])

    def test_preserve_candidate_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="33333333-3333-3333-3333-333333333333", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            # Swap order -> should invalidate (builder sorts by rank, so original order is sorted)
            data["candidates"] = list(reversed(data["candidates"]))
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])
            self.assertFalse(result["root_hash_valid"])


if __name__ == "__main__":
    unittest.main()
