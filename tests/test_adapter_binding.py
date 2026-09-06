"""Binding tests — real face adapter over face/ module, deterministic string scores, reuse."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.canonical import canonical_dumps
from evidence.schema import VerificationData
from verification.adapter import (
    format_score,
    verify_candidate,
    verify_candidate_with_embedding,
    get_reference_embedding,
    METHOD,
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_LOW_THRESHOLD,
)
from evidence.builder import build_evidence
from verifier.independent import verify_offline


class TestRealAdapterContract(unittest.TestCase):
    def test_score_is_deterministic_string_not_float(self):
        # Mock face matcher to return 0.8734215 -> should be 0.873422 string
        mock_emb = np.zeros(512, dtype=np.float32)
        mock_face_result = {
            "faces_detected": 1, "best_face_index": 0, "best_similarity": 0.8734216,
            "face_similarities": [0.8734216], "status": "success", "quality_status": "GOOD", "error": None
        }
        def fake_get_modules():
            return (MagicMock(return_value={"det_score": 0.99, "bbox": [], "embedding": mock_emb}), MagicMock(return_value=mock_emb), MagicMock(return_value=mock_face_result), MagicMock(return_value="MATCH"))

        # Use get_reference_embedding mock + _get_face_modules mock for inner face call
        with patch("verification.adapter.get_reference_embedding", return_value=(mock_emb, {"det_score": 0.99})):
            with patch("verification.adapter._get_face_modules", return_value=(
                MagicMock(return_value={"det_score": 0.99}), MagicMock(return_value=mock_emb), MagicMock(return_value=mock_face_result), MagicMock(side_effect=lambda s, h=0.70, l=0.40: "MATCH" if s and s>=h else ("NO MATCH" if s is not None and s<=l else "INCONCLUSIVE"))
            )):
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as q:
                    from PIL import Image
                    Image.new("RGB", (10, 10), color="red").save(q.name)
                    cand = q.name
                    try:
                        vd = verify_candidate(q.name, cand)
                    finally:
                        Path(q.name).unlink(missing_ok=True)
                self.assertEqual(vd.score, "0.873422")
                self.assertIsInstance(vd.score, str)
                canonical_dumps({"verification": vd.to_dict()})
                with self.assertRaises(ValueError):
                    canonical_dumps({"verification": {"score": 0.8734215}})

    def test_decision_lowercase_vocab(self):
        mock_emb = np.zeros(512, dtype=np.float32)
        cases = [
            (0.85, "match"),
            (0.25, "no_match"),
            (0.55, "inconclusive"),
            (None, "inconclusive"),
        ]
        for sim, expected in cases:
            with patch("verification.adapter.get_reference_embedding", return_value=(mock_emb, {})):
                face_result = {
                    "faces_detected": 0 if sim is None else 1,
                    "best_face_index": None if sim is None else 0,
                    "best_similarity": sim,
                    "face_similarities": [] if sim is None else [sim],
                    "status": "no_face" if sim is None else "success",
                    "quality_status": "NO_FACE" if sim is None else "GOOD",
                    "error": None
                }
                with patch("verification.adapter._get_face_modules", return_value=(
                    MagicMock(), MagicMock(), MagicMock(return_value=face_result),
                    MagicMock(side_effect=lambda s, h=0.70, l=0.40: "MATCH" if s is not None and s>=h else ("NO MATCH" if s is not None and s<=l else "INCONCLUSIVE"))
                )):
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as q:
                        from PIL import Image
                        Image.new("RGB", (10, 10), color="red").save(q.name)
                        cand = q.name
                        try:
                            vd = verify_candidate(q.name, cand)
                        finally:
                            Path(q.name).unlink(missing_ok=True)
                    self.assertEqual(vd.decision, expected, f"sim {sim} -> {expected}")
                    self.assertIn(vd.decision, {"match", "no_match", "inconclusive", "error"})

    def test_error_and_no_face_maps(self):
        mock_emb = np.zeros(512, dtype=np.float32)
        with patch("verification.adapter.get_reference_embedding", return_value=(mock_emb, {})):
            # no_face
            with patch("verification.adapter._get_face_modules", return_value=(
                MagicMock(), MagicMock(),
                MagicMock(return_value={"faces_detected": 0, "best_face_index": None, "best_similarity": None, "face_similarities": [], "status": "no_face", "quality_status": "NO_FACE", "error": "No face"}),
                MagicMock(return_value="INCONCLUSIVE")
            )):
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as q:
                    from PIL import Image
                    Image.new("RGB", (10, 10), color="red").save(q.name)
                    try:
                        vd = verify_candidate(q.name, q.name)
                    finally:
                        Path(q.name).unlink(missing_ok=True)
                self.assertEqual(vd.decision, "inconclusive")
                self.assertIsNone(vd.score)
                self.assertEqual(vd.candidate_face_detected, False)
            # error
            with patch("verification.adapter._get_face_modules", return_value=(
                MagicMock(), MagicMock(),
                MagicMock(return_value={"faces_detected": 0, "best_face_index": None, "best_similarity": None, "face_similarities": [], "status": "error", "quality_status": "ERROR", "error": "candidate not found"}),
                MagicMock()
            )):
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as q:
                    from PIL import Image
                    Image.new("RGB", (10, 10), color="red").save(q.name)
                    try:
                        vd = verify_candidate(q.name, q.name)
                    finally:
                        Path(q.name).unlink(missing_ok=True)
                self.assertEqual(vd.decision, "error")
                self.assertIsNone(vd.score)

    def test_method_is_real_not_stub(self):
        self.assertNotEqual(METHOD, "stub-hash-v1")
        self.assertIn("insightface", METHOD)
        mock_emb = np.zeros(512, dtype=np.float32)
        with patch("verification.adapter.get_reference_embedding", return_value=(mock_emb, {})):
            with patch("verification.adapter._get_face_modules", return_value=(
                MagicMock(), MagicMock(),
                MagicMock(return_value={"faces_detected": 1, "best_face_index": 0, "best_similarity": 0.8, "face_similarities": [0.8], "status": "success", "quality_status": "GOOD", "error": None}),
                MagicMock(return_value="MATCH")
            )):
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as q:
                    from PIL import Image
                    Image.new("RGB", (10, 10), color="red").save(q.name)
                    try:
                        vd = verify_candidate(q.name, q.name)
                    finally:
                        Path(q.name).unlink(missing_ok=True)
                self.assertEqual(vd.method, METHOD)

    def test_verify_candidate_with_embedding_scores(self):
        emb = np.random.randn(512).astype(np.float32)
        with patch("verification.adapter._get_face_modules", return_value=(
            MagicMock(), MagicMock(),
            MagicMock(return_value={"faces_detected": 1, "best_face_index": 0, "best_similarity": 0.912345, "face_similarities": [0.912345], "status": "success", "quality_status": "GOOD", "error": None}),
            MagicMock(return_value="MATCH")
        )):
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                from PIL import Image
                Image.new("RGB", (10, 10), color="blue").save(tmp.name)
                try:
                    vd = verify_candidate_with_embedding(emb, tmp.name)
                finally:
                    Path(tmp.name).unlink(missing_ok=True)
            self.assertEqual(vd.score, "0.912345")
            self.assertEqual(vd.decision, "match")


class TestPipelineReuse(unittest.TestCase):
    def test_query_embedding_used_once(self):
        # Verify pipeline reuses query embedding: get_reference_embedding called exactly 1 time for N candidates
        import tempfile
        from unittest.mock import patch
        import numpy as np
        from evidence.schema import VerificationData

        with tempfile.TemporaryDirectory() as tmpdir:
            q = Path(tmpdir) / "query.jpg"
            c1 = Path(tmpdir) / "c1.jpg"
            c2 = Path(tmpdir) / "c2.jpg"
            c3 = Path(tmpdir) / "c3.jpg"
            from PIL import Image
            for p in [q, c1, c2, c3]:
                Image.new("RGB", (10, 10), color="red").save(p)
            manifest = {
                "query_image": str(q),
                "candidate_count": 3,
                "acquired_count": 3,
                "failed_count": 0,
                "timestamp": "2026-09-06T12:00:00+00:00",
                "candidates": [
                    {"candidate_id": "cand_001", "status": "success", "provider": "visual-search-acquisition", "local_path": str(c1), "content_sha256": "a"*64, "image_url": "https://example.com/a.jpg", "thumbnail_url": None, "title": None, "search_rank": 1, "discovery_provider": "yandex-visual-search"},
                    {"candidate_id": "cand_002", "status": "success", "provider": "visual-search-acquisition", "local_path": str(c2), "content_sha256": "b"*64, "image_url": "https://example.com/b.jpg", "thumbnail_url": None, "title": None, "search_rank": 2, "discovery_provider": "yandex-visual-search"},
                    {"candidate_id": "cand_003", "status": "success", "provider": "visual-search-acquisition", "local_path": str(c3), "content_sha256": "c"*64, "image_url": "https://example.com/c.jpg", "thumbnail_url": None, "title": None, "search_rank": 3, "discovery_provider": "yandex-visual-search"},
                ],
            }
            mock_emb = np.zeros(512, dtype=np.float32)
            mock_vd = VerificationData(method=METHOD, score="0.800000", decision="match", timestamp="2026-09-06T12:00:00+00:00", query_face_detected=True, candidate_face_detected=True)
            with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
                with patch("verification.adapter.get_reference_embedding", return_value=(mock_emb, {"det_score": 0.99})) as mock_get:
                    with patch("verification.adapter.verify_candidate_with_embedding", return_value=mock_vd) as mock_verify:
                        from pipeline import run_full_pipeline
                        result = run_full_pipeline(
                            image_path=str(q),
                            register_on_chain=False,
                            evidence_output_dir=str(Path(tmpdir) / "ev"),
                            anchor_dir=str(Path(tmpdir) / "bl"),
                        )
                        # get_reference_embedding must be called exactly once, not 3 times
                        self.assertEqual(mock_get.call_count, 1)
                        # verify per candidate
                        self.assertEqual(mock_verify.call_count, 3)
                        # all candidates should have match decision
                        for c in result["envelope"].candidates:
                            self.assertEqual(c.verification.decision, "match")
                            self.assertEqual(c.verification.score, "0.800000")

    def test_mockable_integration_no_network(self):
        # Ensure run_full_pipeline remains mockable without live Yandex
        import tempfile
        from unittest.mock import patch
        import numpy as np
        from evidence.schema import VerificationData
        with tempfile.TemporaryDirectory() as tmpdir:
            q = Path(tmpdir) / "query.jpg"
            from PIL import Image
            Image.new("RGB", (10, 10), color="red").save(q)
            manifest = {
                "query_image": str(q),
                "candidate_count": 1,
                "acquired_count": 1,
                "failed_count": 0,
                "timestamp": "2026-09-06T12:00:00+00:00",
                "candidates": [
                    {"candidate_id": "cand_001", "status": "success", "provider": "visual-search-acquisition", "local_path": str(q), "content_sha256": "a"*64, "image_url": "https://example.com/a.jpg", "thumbnail_url": None, "title": None, "search_rank": 1, "discovery_provider": "yandex-visual-search"},
                ],
            }
            mock_emb = np.zeros(512, dtype=np.float32)
            mock_vd = VerificationData(method=METHOD, score="0.123456", decision="no_match", timestamp="2026-09-06T12:00:00+00:00", query_face_detected=True, candidate_face_detected=True)
            with patch("search.acquisition.runner.run_pipeline", return_value=manifest):
                with patch("verification.adapter.get_reference_embedding", return_value=(mock_emb, {})):
                    with patch("verification.adapter.verify_candidate_with_embedding", return_value=mock_vd):
                        from pipeline import run_full_pipeline
                        from verifier.independent import verify_offline
                        result = run_full_pipeline(
                            image_path=str(q),
                            register_on_chain=False,
                            evidence_output_dir=str(Path(tmpdir) / "ev"),
                            anchor_dir=str(Path(tmpdir) / "bl"),
                        )
                        self.assertEqual(result["envelope"].candidates[0].verification.decision, "no_match")
                        # evidence must be verifiable offline
                        ev_path = Path(tmpdir) / "ev" / f"evidence_{result['envelope'].pipeline_run_id}.json"
                        self.assertTrue(ev_path.exists())
                        ver = verify_offline(ev_path)
                        self.assertTrue(ver["valid"])
