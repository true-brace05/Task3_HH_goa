"""Phase 4 face verification integration tests — mocked, no GPU/model download."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.builder import build_evidence
from evidence.schema import VerificationData
from verifier.independent import verify_offline
from blockchain.client import InMemoryBlockchainClient
from blockchain.registration import register_evidence
from verification.adapter import format_score, verify_candidate, METHOD


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


def make_verification(method=METHOD, score="0.873421", decision="match", error=None, q_detected=True, c_detected=True):
    return {
        "method": method,
        "score": score,
        "decision": decision,
        "timestamp": "2026-09-06T12:00:00+00:00",
        "query_face_detected": q_detected,
        "candidate_face_detected": c_detected,
        "error": error,
    }


class TestFaceVerificationContract(unittest.TestCase):
    def test_match_result(self):
        manifest = dict(FIXTURE_MANIFEST)
        manifest["candidates"] = [
            {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score="0.912345", decision="match")},
            {**FIXTURE_MANIFEST["candidates"][1], "verification": make_verification(score="0.923456", decision="match")},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", output_dir=tmpdir, write_files=False)
            # verification metadata enters evidence
            self.assertEqual(env.candidates[0].verification.decision, "match")
            self.assertEqual(env.candidates[0].verification.score, "0.912345")
            self.assertIsNotNone(env.candidates[0].evidence_hash)
            self.assertIsNotNone(env.evidence_hash)
            # root includes it
            self.assertTrue(env.evidence_hash)

    def test_no_match_result(self):
        manifest = dict(FIXTURE_MANIFEST)
        manifest["candidates"] = [
            {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score="0.123456", decision="no_match")},
            {**FIXTURE_MANIFEST["candidates"][1], "verification": make_verification(score="0.234567", decision="no_match")},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", output_dir=tmpdir, write_files=False)
            self.assertEqual(env.candidates[0].verification.decision, "no_match")
            self.assertIsNotNone(env.candidates[0].evidence_hash)
            self.assertIsNotNone(env.evidence_hash)

    def test_inconclusive_no_face(self):
        manifest = dict(FIXTURE_MANIFEST)
        manifest["candidates"] = [
            {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score=None, decision="inconclusive", q_detected=True, c_detected=False)},
            {**FIXTURE_MANIFEST["candidates"][1], "verification": make_verification(score=None, decision="inconclusive", q_detected=False, c_detected=False)},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="cccccccc-cccc-cccc-cccc-cccccccccccc", output_dir=tmpdir, write_files=False)
            self.assertEqual(env.candidates[0].verification.decision, "inconclusive")
            self.assertIsNone(env.candidates[0].verification.score)
            self.assertIsNotNone(env.evidence_hash)  # still valid

    def test_error_result(self):
        manifest = dict(FIXTURE_MANIFEST)
        manifest["candidates"] = [
            {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score=None, decision="error", error="corrupted image")},
            {**FIXTURE_MANIFEST["candidates"][1], "verification": make_verification(score="0.800000", decision="match")},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="dddddddd-dddd-dddd-dddd-dddddddddddd", output_dir=tmpdir, write_files=False)
            self.assertEqual(env.candidates[0].verification.decision, "error")
            self.assertEqual(env.candidates[0].verification.error, "corrupted image")
            self.assertIsNotNone(env.candidates[1].evidence_hash)
            # pipeline does not crash
            self.assertIsNotNone(env.evidence_hash)

    def test_verification_tampering_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = dict(FIXTURE_MANIFEST)
            manifest["candidates"] = [
                {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score="0.800000", decision="match")},
                {**FIXTURE_MANIFEST["candidates"][1], "verification": make_verification(score="0.800000", decision="match")},
            ]
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            data["candidates"][0]["verification"]["score"] = "0.900000"
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])
            self.assertFalse(result["candidate_hashes_valid"])
            self.assertFalse(result["root_hash_valid"])

    def test_verification_tampering_decision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = dict(FIXTURE_MANIFEST)
            manifest["candidates"] = [
                {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score="0.800000", decision="match")},
            ]
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="ffffffff-ffff-ffff-ffff-ffffffffffff", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            data["candidates"][0]["verification"]["decision"] = "no_match"
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])
            self.assertTrue(any(m["type"] == "candidate_hash_mismatch" for m in result["mismatches"]))

    def test_verification_tampering_method(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = dict(FIXTURE_MANIFEST)
            manifest["candidates"] = [
                {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score="0.800000", decision="match", method="stub-hash-v1")},
            ]
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="11111111-1111-1111-1111-111111111111", output_dir=tmpdir, write_files=True)
            evidence_path = Path(tmpdir) / f"evidence_{env.pipeline_run_id}.json"
            data = json.loads(evidence_path.read_text())
            data["candidates"][0]["verification"]["method"] = "different-method"
            evidence_path.write_text(json.dumps(data, indent=2))
            result = verify_offline(evidence_path)
            self.assertFalse(result["valid"])

    def test_score_string_precision(self):
        # format_score is single well-defined location with 6 decimals
        self.assertEqual(format_score(0.873421), "0.873421")
        self.assertEqual(format_score(0.1), "0.100000")
        self.assertEqual(format_score(1.0), "1.000000")
        # canonical must not reject string scores
        from evidence.canonical import canonical_dumps
        data = {"verification": {"score": "0.873421", "decision": "match"}}
        # should not raise
        canonical_dumps(data)
        # float would raise
        with self.assertRaises(ValueError):
            canonical_dumps({"verification": {"score": 0.873421}})

    def test_blockchain_integration_with_verification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            manifest = dict(FIXTURE_MANIFEST)
            manifest["candidates"] = [
                {**FIXTURE_MANIFEST["candidates"][0], "verification": make_verification(score="0.800000", decision="match")},
                {**FIXTURE_MANIFEST["candidates"][1], "verification": make_verification(score="0.200000", decision="no_match")},
            ]
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="22222222-2222-2222-2222-222222222222", output_dir=str(evidence_dir), write_files=True)
            evidence_path = evidence_dir / f"evidence_{env.pipeline_run_id}.json"
            client = InMemoryBlockchainClient()
            register_evidence(env, client, anchor_dir=str(anchor_dir), write_anchor=True)
            result = verify_offline(evidence_path, client=client, anchor_dir=str(anchor_dir))
            self.assertTrue(result["valid"])
            self.assertTrue(result["on_chain"])

    def test_pipeline_without_blockchain_with_verification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "evidence"
            anchor_dir = Path(tmpdir) / "blockchain"
            evidence_dir.mkdir()
            anchor_dir.mkdir()
            # Mock verification adapter to return deterministic match
            mock_ver = VerificationData(method="stub-hash-v1", score="0.900000", decision="match", timestamp="2026-09-06T12:00:00+00:00", query_face_detected=True, candidate_face_detected=True)
            with patch("verification.adapter.verify_candidate", return_value=mock_ver):
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
                    # verification results present
                    self.assertIn("verification_results", result)
                    # offline verifier valid
                    evidence_path = evidence_dir / f"evidence_{result['envelope'].pipeline_run_id}.json"
                    ver = verify_offline(evidence_path)
                    self.assertTrue(ver["valid"])
                    self.assertIsNone(ver["on_chain"])

    def test_one_failed_verification_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create real temp images for stub to handle
            q = Path(tmpdir) / "query.jpg"
            from PIL import Image
            Image.new("RGB", (10, 10), color="red").save(q)
            c1 = Path(tmpdir) / "c1.jpg"
            Image.new("RGB", (10, 10), color="blue").save(c1)
            c2_missing = Path(tmpdir) / "missing.jpg"  # does not exist
            # Mock manifest with one good, one missing
            manifest = {
                "query_image": str(q),
                "candidate_count": 2,
                "acquired_count": 2,
                "failed_count": 0,
                "timestamp": "2026-09-06T12:00:00+00:00",
                "candidates": [
                    {"candidate_id": "cand_001", "status": "success", "provider": "visual-search-acquisition", "local_path": str(c1), "content_sha256": "a"*64, "source_url": "https://example.com/p1", "image_url": "https://example.com/img1.jpg", "thumbnail_url": None, "title": None, "search_rank": 1, "discovery_provider": "yandex-visual-search"},
                    {"candidate_id": "cand_002", "status": "success", "provider": "visual-search-acquisition", "local_path": str(c2_missing), "content_sha256": "b"*64, "source_url": "https://example.com/p2", "image_url": "https://example.com/img2.jpg", "thumbnail_url": None, "title": None, "search_rank": 2, "discovery_provider": "yandex-visual-search"},
                ],
            }
            with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
                from pipeline import run_full_pipeline
                result = run_full_pipeline(
                    image_path=str(q),
                    register_on_chain=False,
                    evidence_output_dir=str(Path(tmpdir) / "ev"),
                    anchor_dir=str(Path(tmpdir) / "bl"),
                )
                # Should have 2 candidates, one with error decision
                self.assertEqual(len(result["envelope"].candidates), 2)
                decisions = [c.verification.decision for c in result["envelope"].candidates]
                self.assertIn("error", decisions)
                # Pipeline did not crash, evidence valid
                self.assertIsNotNone(result["envelope"].evidence_hash)


if __name__ == "__main__":
    unittest.main()
