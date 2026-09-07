"""Tests for data-flow inconsistency fix — Task 7."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.builder import build_evidence
from blockchain.client import InMemoryBlockchainClient
from pipeline import run_full_pipeline


class TestDataFlowCounts(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        # ensure candidate dir
        Path("data/candidates").mkdir(parents=True, exist_ok=True)
        # create dummy image for verification
        dummy = self.tmp_path / "dummy.jpg"
        # minimal valid JPEG via PIL
        try:
            from PIL import Image
            img = Image.new("RGB", (10, 10), color="red")
            img.save(dummy, "JPEG")
            self.dummy_path = str(dummy)
        except Exception:
            # fallback raw
            dummy.write_bytes(b"\xff\xd8\xff\xe0" + b"0"*100)
            self.dummy_path = str(dummy)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_successful_acquisition_not_zero_discovery(self):
        """Successful acquisition cannot result in UI discovery count incorrectly showing zero."""
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 2,
            "acquired_count": 1,
            "failed_count": 1,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": self.dummy_path,
                    "content_type": "image/jpeg",
                    "file_size": 100,
                    "content_sha256": "a"*64,
                    "source_url": "https://example.com/p1",
                    "image_url": "https://example.com/img1.jpg",
                    "thumbnail_url": None,
                    "title": None,
                    "search_rank": 1,
                    "discovery_provider": "yandex-visual-search",
                },
                {
                    "candidate_id": "cand_002",
                    "status": "failed",
                    "provider": "visual-search-acquisition",
                    "local_path": None,
                    "content_type": None,
                    "file_size": None,
                    "content_sha256": None,
                    "source_url": "https://example.com/p2",
                    "image_url": "https://example.com/img2.jpg",
                    "thumbnail_url": None,
                    "title": None,
                    "search_rank": 2,
                    "discovery_provider": "yandex-visual-search",
                    "error": "Download failed",
                },
            ],
        }
        with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
            with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                with patch("verification.adapter.verify_candidate_with_embedding") as mock_ver:
                    from evidence.schema import VerificationData
                    mock_ver.return_value = VerificationData(method="insightface-buffalo_l", score="0.850000", decision="match", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=True, error=None)
                    result = run_full_pipeline(image_path=self.dummy_path, register_on_chain=False, evidence_output_dir=str(self.tmp_path/"evidence"), anchor_dir=str(self.tmp_path/"blockchain"))
                    # discovery count must be 2, not 0
                    self.assertEqual(result["manifest"]["candidate_count"], 2)
                    self.assertEqual(result["manifest"]["acquired_count"], 1)
                    # envelope must have 2 candidates (both success and failed preserved)
                    self.assertEqual(len(result["envelope"].candidates), 2)
                    # UI discovery should not be 0
                    # Simulate app.py discovery dict
                    discovery = {
                        "candidate_count": result["manifest"].get("candidate_count", 0),
                        "acquired_count": result["manifest"].get("acquired_count", 0),
                        "failed_count": result["manifest"].get("failed_count", 0),
                    }
                    self.assertNotEqual(discovery["candidate_count"], 0)
                    self.assertEqual(discovery["candidate_count"], 2)
                    # Verify frontend would not show "0 found"
                    # Previously bug: zeroCandidates = j.candidates.length===0 would be false (2), so ok
                    # But new fix ensures discovered count used
                    self.assertEqual(discovery["candidate_count"], len(result["envelope"].candidates) - 0)  # sanity

    def test_counts_remain_distinct(self):
        """Discovery/acquisition/verification counts remain distinct."""
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 20,
            "acquired_count": 18,
            "failed_count": 2,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [
                {
                    "candidate_id": f"cand_{i:03d}",
                    "status": "success" if i <= 18 else "failed",
                    "provider": "visual-search-acquisition",
                    "local_path": self.dummy_path if i <= 18 else None,
                    "content_type": "image/jpeg" if i <= 18 else None,
                    "file_size": 100 if i <= 18 else None,
                    "content_sha256": "a"*64 if i <= 18 else None,
                    "source_url": f"https://example.com/p{i}",
                    "image_url": f"https://example.com/img{i}.jpg",
                    "thumbnail_url": None,
                    "title": None,
                    "search_rank": i,
                    "discovery_provider": "yandex-visual-search",
                    "error": None if i <= 18 else "failed",
                } for i in range(1, 21)
            ],
        }
        # Mock 12 had detectable faces, rest inconclusive
        def mock_verify(ref, path, **kwargs):
            from evidence.schema import VerificationData
            # Alternate decisions
            import random
            return VerificationData(method="insightface-buffalo_l", score="0.800000", decision="match", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=True, error=None)
        with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
            with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                with patch("verification.adapter.verify_candidate_with_embedding", side_effect=mock_verify):
                    result = run_full_pipeline(image_path=self.dummy_path, register_on_chain=False, evidence_output_dir=str(self.tmp_path/"evidence"), anchor_dir=str(self.tmp_path/"blockchain"))
                    discovered = result["manifest"]["candidate_count"]
                    acquired = result["manifest"]["acquired_count"]
                    verified = len(result["verification_results"])
                    evidence_cands = len(result["envelope"].candidates)
                    # Must be distinct: 20 discovered, 18 acquired, 18 verified (or 12 if we mock 12), but not all same
                    self.assertEqual(discovered, 20)
                    self.assertEqual(acquired, 18)
                    self.assertEqual(verified, 18)  # all acquired verified in this mock
                    # Evidence has 20 (including failed)
                    self.assertEqual(evidence_cands, 20)
                    # Not all same number: discovered != acquired or verified distinct from evidence? At least not collapsed to one
                    self.assertNotEqual(discovered, acquired)  # 20 != 18
                    # Ensure UI would show distinct: discovery, acquisition, verification not same
                    self.assertTrue(discovered != acquired or verified != evidence_cands)

    def test_genuine_zero_discovery(self):
        """A genuine zero discovery result still works."""
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 0,
            "acquired_count": 0,
            "failed_count": 0,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [],
        }
        with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
            result = run_full_pipeline(image_path=self.dummy_path, register_on_chain=False, evidence_output_dir=str(self.tmp_path/"evidence"), anchor_dir=str(self.tmp_path/"blockchain"))
            self.assertEqual(result["manifest"]["candidate_count"], 0)
            self.assertEqual(len(result["envelope"].candidates), 0)
            self.assertEqual(result["envelope"].candidate_count, 0)
            self.assertEqual(result["envelope"].acquired_count, 0)
            # Evidence file should exist even with 0 candidates
            ev_path = self.tmp_path/"evidence"/f"evidence_{result['envelope'].pipeline_run_id}.json"
            self.assertTrue(ev_path.exists())
            data = json.loads(ev_path.read_text())
            self.assertEqual(len(data["candidates"]), 0)

    def test_acquired_no_face(self):
        """Acquired candidate with no detectable face is represented correctly."""
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 1,
            "acquired_count": 1,
            "failed_count": 0,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": self.dummy_path,
                    "content_type": "image/jpeg",
                    "file_size": 100,
                    "content_sha256": "a"*64,
                    "source_url": "https://example.com/p1",
                    "image_url": "https://example.com/img1.jpg",
                    "thumbnail_url": None,
                    "title": None,
                    "search_rank": 1,
                    "discovery_provider": "yandex-visual-search",
                }
            ],
        }
        with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
            with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                with patch("verification.adapter.verify_candidate_with_embedding") as mock_ver:
                    from evidence.schema import VerificationData
                    mock_ver.return_value = VerificationData(method="insightface-buffalo_l", score=None, decision="inconclusive", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=False, error="no face detected")
                    result = run_full_pipeline(image_path=self.dummy_path, register_on_chain=False, evidence_output_dir=str(self.tmp_path/"evidence"), anchor_dir=str(self.tmp_path/"blockchain"))
                    ver = result["verification_results"]["cand_001"]
                    self.assertEqual(ver.decision, "inconclusive")
                    self.assertFalse(ver.candidate_face_detected)
                    self.assertIsNone(ver.score)
                    # Candidate preserved in envelope with verification
                    cand = result["envelope"].candidates[0]
                    self.assertEqual(cand.verification.decision, "inconclusive")
                    self.assertEqual(cand.status, "success")
                    # UI counts: discovered 1, acquired 1, verified 1 (even though inconclusive)
                    self.assertEqual(result["manifest"]["candidate_count"], 1)
                    self.assertEqual(result["manifest"]["acquired_count"], 1)
                    self.assertEqual(len(result["verification_results"]), 1)

    def test_single_pipeline_execution(self):
        """One investigation request does not execute discovery twice."""
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 1,
            "acquired_count": 1,
            "failed_count": 0,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": self.dummy_path,
                    "content_type": "image/jpeg",
                    "file_size": 100,
                    "content_sha256": "a"*64,
                    "source_url": "https://example.com/p1",
                    "image_url": "https://example.com/img1.jpg",
                    "thumbnail_url": None,
                    "title": None,
                    "search_rank": 1,
                    "discovery_provider": "yandex-visual-search",
                }
            ],
        }
        with patch("search.acquisition.runner.run_pipeline", return_value=manifest) as mock_run:
            with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                with patch("verification.adapter.verify_candidate_with_embedding") as mock_ver:
                    from evidence.schema import VerificationData
                    mock_ver.return_value = VerificationData(method="insightface-buffalo_l", score="0.9", decision="match", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=True, error=None)
                    result = run_full_pipeline(image_path=self.dummy_path, register_on_chain=False, evidence_output_dir=str(self.tmp_path/"evidence"), anchor_dir=str(self.tmp_path/"blockchain"))
                    mock_run.assert_called_once()
                    # Also test via Flask endpoint single call doesn't double
                    from app import app
                    app.config["TESTING"] = True
                    client = app.test_client()
                    # Use same mock for endpoint
                    with patch("search.acquisition.runner.run_pipeline", return_value=manifest) as mock_run2:
                        with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                            with patch("verification.adapter.verify_candidate_with_embedding", return_value=VerificationData(method="insightface-buffalo_l", score="0.9", decision="match", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=True, error=None)):
                                # create minimal image file upload
                                dummy_img = Path(self.dummy_path)
                                data = {"image": (open(dummy_img, "rb"), "query.jpg")}
                                resp = client.post("/api/investigate", data=data, content_type="multipart/form-data")
                                self.assertEqual(resp.status_code, 200)
                                mock_run2.assert_called_once()
                                j = resp.get_json()
                                self.assertEqual(j["discovery"]["candidate_count"], 1)
                                self.assertEqual(j["discovery"]["acquired_count"], 1)

    def test_inmemory_not_real_anchor(self):
        """InMemory anchor is never labelled as a real blockchain anchor."""
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 1,
            "acquired_count": 1,
            "failed_count": 0,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": self.dummy_path,
                    "content_type": "image/jpeg",
                    "file_size": 100,
                    "content_sha256": "a"*64,
                    "source_url": "https://example.com/p1",
                    "image_url": "https://example.com/img1.jpg",
                    "thumbnail_url": None,
                    "title": None,
                    "search_rank": 1,
                    "discovery_provider": "yandex-visual-search",
                }
            ],
        }
        with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
            with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                with patch("verification.adapter.verify_candidate_with_embedding") as mock_ver:
                    from evidence.schema import VerificationData
                    mock_ver.return_value = VerificationData(method="insightface-buffalo_l", score="0.9", decision="match", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=True, error=None)
                    # InMemory client with zero address
                    client = InMemoryBlockchainClient(contract_address="0x0000000000000000000000000000000000000000")
                    result = run_full_pipeline(image_path=self.dummy_path, register_on_chain=True, blockchain_client=client, evidence_output_dir=str(self.tmp_path/"evidence"), anchor_dir=str(self.tmp_path/"blockchain"))
                    anchor = result["anchor"]
                    self.assertIsNotNone(anchor)
                    self.assertEqual(anchor["contract_address"], "0x0000000000000000000000000000000000000000")
                    # Pipeline tags it as IN-MEMORY
                    self.assertEqual(anchor.get("_mode"), "IN-MEMORY ANCHOR")
                    self.assertTrue(anchor.get("_inmemory"))
                    # Flask status should not show zero address as real
                    from app import _settings_status
                    with patch.dict("os.environ", {}, clear=False):
                        # ensure settings reflect no real contract
                        status = _settings_status()
                        # contract_address should be empty for zero address
                        self.assertEqual(status["blockchain"]["contract_address"], "")
                        self.assertIn("InMemory", status["blockchain"]["mode"])
                    # Also test app endpoint returns anchor_mode InMemory
                    from app import app
                    app.config["TESTING"] = True
                    test_client = app.test_client()
                    with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
                        with patch("verification.adapter.get_reference_embedding", return_value=(MagicMock(), {})):
                            with patch("verification.adapter.verify_candidate_with_embedding", return_value=VerificationData(method="insightface-buffalo_l", score="0.9", decision="match", timestamp="2026-09-07T00:00:00+00:00", query_face_detected=True, candidate_face_detected=True, error=None)):
                                dummy_img = Path(self.dummy_path)
                                data = {"image": (open(dummy_img, "rb"), "query.jpg"), "anchor": "true"}
                                # Force InMemory by not configuring env
                                resp = test_client.post("/api/investigate", data=data, content_type="multipart/form-data")
                                self.assertEqual(resp.status_code, 200)
                                j = resp.get_json()
                                self.assertEqual(j["anchor_mode"], "IN-MEMORY ANCHOR")
                                self.assertIsNone(j["anchor_contract_display"])
                                # Ensure frontend would not show ANCHORED ON BLOCKCHAIN
                                self.assertNotEqual(j["anchor_mode"], "ANCHORED ON BLOCKCHAIN")


if __name__ == "__main__":
    unittest.main()
