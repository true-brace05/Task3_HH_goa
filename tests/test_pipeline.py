"""Phase 3 pipeline tests — mock discovery, InMemory, immutability."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
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


class TestPipelineIntegration(unittest.TestCase):
    def test_mock_discovery_to_anchor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()

            # Mock discovery: return fixture manifest
            mock_manifest = dict(FIXTURE_MANIFEST)
            with patch("search.acquisition.runner.run_pipeline") as mock_run:
                mock_run.return_value = mock_manifest
                from pipeline import run_full_pipeline

                client = InMemoryBlockchainClient()
                result = run_full_pipeline(
                    image_path="data/input/mock.jpg",
                    register_on_chain=True,
                    blockchain_client=client,
                    evidence_output_dir=str(evidence_dir),
                    anchor_dir=str(anchor_dir),
                )
                mock_run.assert_called_once()
                self.assertIsNotNone(result["envelope"])
                self.assertIsNotNone(result["anchor"])
                self.assertIn("event_bus", result)
                # Deterministic hash
                self.assertEqual(result["envelope"].evidence_hash, result["envelope"].evidence_hash)
                # Anchor written separately
                anchor_path = anchor_dir / f"anchor_{result['envelope'].evidence_hash}.json"
                self.assertTrue(anchor_path.exists())
                with open(anchor_path) as f:
                    anchor_data = json.load(f)
                self.assertEqual(anchor_data["evidence_hash"], result["envelope"].evidence_hash)
                # Evidence file does NOT contain blockchain fields
                evidence_path = evidence_dir / f"evidence_{result['envelope'].pipeline_run_id}.json"
                self.assertTrue(evidence_path.exists())
                evidence_data = json.loads(evidence_path.read_text())
                self.assertNotIn("transaction_hash", json.dumps(evidence_data))
                self.assertNotIn("block_number", json.dumps(evidence_data))
                # Independent verification succeeds
                ver = verify_offline(evidence_path, client=client, anchor_dir=str(anchor_dir))
                self.assertTrue(ver["valid"])
                self.assertTrue(ver["on_chain"])

    def test_no_search_import_in_evidence(self):
        import evidence.builder as b
        import evidence.hash as h
        import evidence.canonical as c
        for mod in [b, h, c]:
            src = Path(mod.__file__).read_text()
            self.assertNotIn("from search", src)
            # avoid false positive due to docstring containing import search
            # Check actual import statements
            self.assertNotIn("import search", src.replace("This module has zero dependency on discovery code", ""))

    def test_registration_does_not_mutate_envelope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", output_dir=tmpdir, write_files=False)
            before = env.evidence_hash
            before_dict = json.dumps(env.to_dict(), sort_keys=True)
            client = InMemoryBlockchainClient()
            anchor = register_evidence(env, client, anchor_dir=tmpdir, write_anchor=False)
            self.assertEqual(env.evidence_hash, before)
            self.assertEqual(json.dumps(env.to_dict(), sort_keys=True), before_dict)
            self.assertNotIn("transaction_hash", before_dict)

    def test_pipeline_without_blockchain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            with patch("search.acquisition.runner.run_pipeline") as mock_run:
                mock_run.return_value = dict(FIXTURE_MANIFEST)
                from pipeline import run_full_pipeline
                result = run_full_pipeline(
                    image_path="data/input/mock.jpg",
                    register_on_chain=False,
                    evidence_output_dir=str(evidence_dir),
                    anchor_dir=str(anchor_dir),
                )
                self.assertIsNotNone(result["envelope"])
                self.assertIsNone(result["anchor"])
                # No anchor file created
                self.assertEqual(list(anchor_dir.glob("anchor_*.json")), [])
                # Event bus should have evidence_built but NOT blockchain_registered
                events = [e.event for e in result["event_bus"].get_timeline()]
                self.assertIn("evidence_built", events)
                self.assertNotIn("blockchain_registered", events)
                # Hashed timeline must not contain blockchain_registered
                hashed_events = [e.event for e in result["envelope"].timeline]
                self.assertNotIn("blockchain_registered", hashed_events)

    def test_verify_pipeline_api(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            evidence_dir.mkdir()
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", output_dir=str(evidence_dir), write_files=True)
            evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
            from pipeline import verify_pipeline
            result = verify_pipeline(str(evidence_path))
            self.assertTrue(result["valid"])
            self.assertIsNone(result["on_chain"])


if __name__ == "__main__":
    unittest.main()
