"""Unit and integration tests for Face Verification Pipeline integration (Step 4)."""

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

from face.pipeline import run_face_pipeline


class TestFacePipelineIntegration(unittest.TestCase):
    """Test the integrated face verification pipeline with discovery and candidate acquisition."""

    @classmethod
    def setUpClass(cls):
        cls.query_image = Path("data/test_faces/person1_a.jpg")
        cls.cand_same = Path("data/test_faces/person1_b.jpg")
        cls.cand_diff = Path("data/test_faces/person2_a.jpg")
        cls.cand_multi = Path("data/test_faces/two_faces.jpg")
        cls.cand_noface = Path("data/test_faces/no_face.jpg")

    def test_pipeline_with_mock_discovery_manifest(self):
        """1, 2, 5, 6. Test full pipeline with mock discovery manifest: verification, metadata preservation, and ranking."""
        mock_manifest = {
            "query_image": str(self.query_image),
            "candidate_count": 3,
            "acquisition_attempted": 3,
            "acquired_count": 3,
            "failed_count": 0,
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": str(self.cand_diff),
                    "source_url": "https://example.com/diff",
                    "image_url": "https://example.com/diff.jpg",
                    "title": "Different Person",
                    "search_rank": 1,
                    "content_sha256": "1" * 64,
                    "discovery_provider": "yandex-visual-search",
                },
                {
                    "candidate_id": "cand_002",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": str(self.cand_same),
                    "source_url": "https://example.com/same",
                    "image_url": "https://example.com/same.jpg",
                    "title": "Same Person",
                    "search_rank": 2,
                    "content_sha256": "2" * 64,
                    "discovery_provider": "yandex-visual-search",
                },
                {
                    "candidate_id": "cand_003",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": str(self.cand_multi),
                    "source_url": "https://example.com/multi",
                    "image_url": "https://example.com/multi.jpg",
                    "title": "Two People",
                    "search_rank": 3,
                    "content_sha256": "3" * 64,
                    "discovery_provider": "yandex-visual-search",
                },
            ],
        }

        result = run_face_pipeline(
            reference_image_path=self.query_image,
            high_threshold=0.70,
            low_threshold=0.40,
            discovery_manifest=mock_manifest,
        )

        self.assertTrue(result["reference_face_detected"])
        self.assertEqual(result["candidates_discovered"], 3)
        self.assertEqual(result["candidates_verified"], 3)
        self.assertEqual(len(result["ranked_candidates"]), 3)

        # Ranked #1 should be cand_002 (Same person, similarity > 0.70 -> MATCH)
        rank_1 = result["ranked_candidates"][0]
        self.assertEqual(rank_1["candidate_id"], "cand_002")
        self.assertEqual(rank_1["rank"], 1)
        self.assertEqual(rank_1["decision"], "MATCH")
        self.assertGreater(rank_1["similarity"], 0.70)
        self.assertEqual(rank_1["source_url"], "https://example.com/same")
        self.assertEqual(rank_1["title"], "Same Person")

    def test_failed_acquisition_candidate_handled_safely(self):
        """3, 4. Candidates that failed acquisition or lack local_path are handled safely as INCONCLUSIVE."""
        mock_manifest = {
            "query_image": str(self.query_image),
            "candidate_count": 2,
            "acquired_count": 1,
            "failed_count": 1,
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "failed",
                    "error": "HTTP error: 403 Forbidden",
                    "provider": "visual-search-acquisition",
                    "source_url": "https://example.com/fail",
                    "image_url": "https://example.com/fail.jpg",
                    "search_rank": 1,
                },
                {
                    "candidate_id": "cand_002",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": str(self.cand_same),
                    "source_url": "https://example.com/same",
                    "image_url": "https://example.com/same.jpg",
                    "search_rank": 2,
                },
            ],
        }

        result = run_face_pipeline(
            reference_image_path=self.query_image,
            discovery_manifest=mock_manifest,
        )

        self.assertEqual(len(result["ranked_candidates"]), 2)
        # Succeeded candidate should be Rank 1
        self.assertEqual(result["ranked_candidates"][0]["candidate_id"], "cand_002")
        self.assertEqual(result["ranked_candidates"][0]["rank"], 1)
        self.assertEqual(result["ranked_candidates"][0]["decision"], "MATCH")

        # Failed candidate should be Rank 2 with decision INCONCLUSIVE
        self.assertEqual(result["ranked_candidates"][1]["candidate_id"], "cand_001")
        self.assertEqual(result["ranked_candidates"][1]["rank"], 2)
        self.assertEqual(result["ranked_candidates"][1]["decision"], "INCONCLUSIVE")
        self.assertIsNone(result["ranked_candidates"][1]["similarity"])
        self.assertEqual(result["ranked_candidates"][1]["quality_status"], "ACQUISITION_FAILED")

    def test_invalid_query_stops_pipeline_before_discovery(self):
        """Pipeline rejects 0-face or multi-face reference image with ValueError before discovery."""
        with self.assertRaises(ValueError) as ctx:
            run_face_pipeline(self.cand_noface)
        self.assertIn("No face detected", str(ctx.exception))

    def test_pipeline_saves_debug_verification_results_json(self):
        """Verify that run_face_pipeline automatically writes data/debug/verification_results.json."""
        import json
        debug_file = Path("data/debug/verification_results.json")
        mock_manifest = {
            "query_image": str(self.query_image),
            "candidate_count": 1,
            "acquired_count": 1,
            "failed_count": 0,
            "candidates": [
                {
                    "candidate_id": "cand_001",
                    "status": "success",
                    "provider": "visual-search-acquisition",
                    "local_path": str(self.cand_same),
                    "search_rank": 1,
                }
            ],
        }

        result = run_face_pipeline(
            reference_image_path=self.query_image,
            discovery_manifest=mock_manifest,
            output_path=str(debug_file),
        )

        self.assertTrue(debug_file.exists(), "verification_results.json should be written to disk")
        with open(debug_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["query_image"], str(self.query_image))
        self.assertEqual(len(data["ranked_candidates"]), 1)
        self.assertEqual(data["ranked_candidates"][0]["decision"], "MATCH")


if __name__ == "__main__":
    unittest.main()

