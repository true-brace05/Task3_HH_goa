"""Unit and integration tests for Face Verification POC (Step 3: Ranking & Decision)."""

import unittest
import numpy as np
from pathlib import Path

from face.detector import detect_faces, detect_query_face
from face.embedder import generate_embedding, normalize_embedding
from face.matcher import compute_similarity, verify_candidate, verify_candidate_embeddings
from face.ranking import make_decision, rank_candidates


class TestFaceMathAndEmbeddings(unittest.TestCase):
    """Test mathematical properties of embeddings and cosine similarity."""

    def test_normalize_embedding(self):
        vec = np.array([3.0, 4.0], dtype=np.float32)
        norm_vec = normalize_embedding(vec)
        self.assertAlmostEqual(np.linalg.norm(norm_vec), 1.0, places=5)
        np.testing.assert_allclose(norm_vec, [0.6, 0.8], atol=1e-5)

    def test_normalize_embedding_zero_raises(self):
        vec = np.zeros(512, dtype=np.float32)
        with self.assertRaises(ValueError):
            normalize_embedding(vec)

    def test_cosine_similarity_identical(self):
        vec_a = np.random.randn(512).astype(np.float32)
        sim = compute_similarity(vec_a, vec_a)
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_cosine_similarity_orthogonal(self):
        vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        vec_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        sim = compute_similarity(vec_a, vec_b)
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_cosine_similarity_opposite(self):
        vec_a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        vec_b = np.array([-1.0, -2.0, -3.0], dtype=np.float32)
        sim = compute_similarity(vec_a, vec_b)
        self.assertAlmostEqual(sim, -1.0, places=5)

    def test_cosine_similarity_shape_mismatch_raises(self):
        vec_a = np.random.randn(512).astype(np.float32)
        vec_b = np.random.randn(256).astype(np.float32)
        with self.assertRaises(ValueError):
            compute_similarity(vec_a, vec_b)


class TestCandidateVerificationMath(unittest.TestCase):
    """Test candidate verification logic, multi-face comparison, and max selection using synthetic vectors."""

    def test_verify_candidate_embeddings_max_selection(self):
        ref_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

        # 3 candidate vectors with known similarities: 0.21, 0.78, 0.34
        f0 = np.array([0.21, np.sqrt(1 - 0.21**2), 0.0, 0.0], dtype=np.float32)
        f1 = np.array([0.78, np.sqrt(1 - 0.78**2), 0.0, 0.0], dtype=np.float32)
        f2 = np.array([0.34, np.sqrt(1 - 0.34**2), 0.0, 0.0], dtype=np.float32)

        cand_embeddings = [f0, f1, f2]
        result = verify_candidate_embeddings(ref_vec, cand_embeddings)

        self.assertEqual(result["faces_detected"], 3)
        self.assertEqual(result["best_face_index"], 1, "Best face index should be 1")
        self.assertAlmostEqual(result["best_similarity"], 0.78, places=5)
        self.assertEqual(len(result["face_similarities"]), 3)
        self.assertAlmostEqual(result["face_similarities"][0], 0.21, places=5)
        self.assertAlmostEqual(result["face_similarities"][1], 0.78, places=5)
        self.assertAlmostEqual(result["face_similarities"][2], 0.34, places=5)

        # Verify not average
        average_sim = (0.21 + 0.78 + 0.34) / 3.0
        self.assertNotAlmostEqual(result["best_similarity"], average_sim, places=2)

    def test_verify_candidate_embeddings_zero_faces(self):
        ref_vec = np.random.randn(512).astype(np.float32)
        result = verify_candidate_embeddings(ref_vec, [])
        self.assertEqual(result["faces_detected"], 0)
        self.assertIsNone(result["best_face_index"])
        self.assertIsNone(result["best_similarity"])
        self.assertEqual(result["face_similarities"], [])
        self.assertEqual(result["status"], "no_face")


class TestDecisionLogic(unittest.TestCase):
    """Test 3-state decision classification with boundary conditions."""

    def test_similarity_above_high_threshold_matches(self):
        self.assertEqual(make_decision(0.85, high_threshold=0.70, low_threshold=0.40), "MATCH")

    def test_similarity_below_low_threshold_no_match(self):
        self.assertEqual(make_decision(0.25, high_threshold=0.70, low_threshold=0.40), "NO MATCH")

    def test_similarity_between_thresholds_inconclusive(self):
        self.assertEqual(make_decision(0.55, high_threshold=0.70, low_threshold=0.40), "INCONCLUSIVE")

    def test_similarity_exact_high_threshold_matches(self):
        self.assertEqual(make_decision(0.70, high_threshold=0.70, low_threshold=0.40), "MATCH")

    def test_similarity_exact_low_threshold_no_match(self):
        self.assertEqual(make_decision(0.40, high_threshold=0.70, low_threshold=0.40), "NO MATCH")

    def test_similarity_none_inconclusive(self):
        self.assertEqual(make_decision(None, high_threshold=0.70, low_threshold=0.40), "INCONCLUSIVE")

    def test_invalid_thresholds_raises(self):
        with self.assertRaises(ValueError):
            make_decision(0.50, high_threshold=0.30, low_threshold=0.80)


class TestCandidateRanking(unittest.TestCase):
    """Test candidate ranking order, ID preservation, rank assignment, and safe handling of missing values."""

    def test_candidates_sorted_highest_first(self):
        raw_candidates = [
            {"candidate_id": "cand_A", "best_similarity": 0.61},
            {"candidate_id": "cand_B", "best_similarity": 0.83},
            {"candidate_id": "cand_C", "best_similarity": 0.72},
        ]
        ranked = rank_candidates(raw_candidates, high_threshold=0.70, low_threshold=0.40)

        # Expected order: cand_B (0.83), cand_C (0.72), cand_A (0.61)
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["candidate_id"], "cand_B")
        self.assertEqual(ranked[1]["candidate_id"], "cand_C")
        self.assertEqual(ranked[2]["candidate_id"], "cand_A")

    def test_correct_rank_numbers(self):
        raw_candidates = [
            {"candidate_id": "cand_A", "best_similarity": 0.10},
            {"candidate_id": "cand_B", "best_similarity": 0.90},
        ]
        ranked = rank_candidates(raw_candidates)
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["rank"], 2)

    def test_candidate_id_preserved_and_fallback(self):
        # Case 1: ID provided
        raw_with_id = [{"candidate_id": "cand_custom_999", "best_similarity": 0.88}]
        ranked_with_id = rank_candidates(raw_with_id)
        self.assertEqual(ranked_with_id[0]["candidate_id"], "cand_custom_999")

        # Case 2: ID missing -> fallback generated
        raw_without_id = [{"best_similarity": 0.88}]
        ranked_without_id = rank_candidates(raw_without_id)
        self.assertEqual(ranked_without_id[0]["candidate_id"], "cand_001")

    def test_candidates_with_missing_similarity_handled_safely(self):
        raw_candidates = [
            {"candidate_id": "cand_good", "best_similarity": 0.75},
            {"candidate_id": "cand_no_face", "best_similarity": None},
            {"candidate_id": "cand_low", "best_similarity": 0.20},
        ]
        ranked = rank_candidates(raw_candidates, high_threshold=0.70, low_threshold=0.40)

        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["candidate_id"], "cand_good")
        self.assertEqual(ranked[0]["decision"], "MATCH")

        self.assertEqual(ranked[1]["candidate_id"], "cand_low")
        self.assertEqual(ranked[1]["decision"], "NO MATCH")

        self.assertEqual(ranked[2]["candidate_id"], "cand_no_face")
        self.assertIsNone(ranked[2]["similarity"])
        self.assertEqual(ranked[2]["decision"], "INCONCLUSIVE")

    def test_empty_candidates_list(self):
        ranked = rank_candidates([])
        self.assertEqual(ranked, [])


class TestFaceDetectorAndValidation(unittest.TestCase):
    """Test face detection and query image validation rules with image files."""

    @classmethod
    def setUpClass(cls):
        cls.img_person1_a = Path("data/test_faces/person1_a.jpg")
        cls.img_person1_b = Path("data/test_faces/person1_b.jpg")
        cls.img_person2_a = Path("data/test_faces/person2_a.jpg")
        cls.img_two_faces = Path("data/test_faces/two_faces.jpg")
        cls.img_no_face = Path("data/test_faces/no_face.jpg")

    def test_reference_single_face_accepted(self):
        if not self.img_person1_a.exists():
            self.skipTest("Test image person1_a.jpg not found")
        face = detect_query_face(self.img_person1_a)
        self.assertIsInstance(face, dict)
        self.assertIn("embedding", face)
        self.assertGreater(face["det_score"], 0.5)

    def test_reference_zero_faces_rejected(self):
        if not self.img_no_face.exists():
            self.skipTest("Test image no_face.jpg not found")
        with self.assertRaises(ValueError) as ctx:
            detect_query_face(self.img_no_face)
        self.assertIn("No face detected", str(ctx.exception))

    def test_reference_multiple_faces_rejected(self):
        if not self.img_two_faces.exists():
            self.skipTest("Test image two_faces.jpg not found")
        with self.assertRaises(ValueError) as ctx:
            detect_query_face(self.img_two_faces)
        self.assertIn("Multiple faces", str(ctx.exception))


class TestCandidateVerificationIntegration(unittest.TestCase):
    """Test end-to-end candidate verification with single-face, multi-face, and no-face candidate images."""

    @classmethod
    def setUpClass(cls):
        cls.img_person1_a = Path("data/test_faces/person1_a.jpg")
        cls.img_person1_b = Path("data/test_faces/person1_b.jpg")
        cls.img_person2_a = Path("data/test_faces/person2_a.jpg")
        cls.img_two_faces = Path("data/test_faces/two_faces.jpg")
        cls.img_no_face = Path("data/test_faces/no_face.jpg")
        if cls.img_person1_a.exists():
            cls.ref_embedding = generate_embedding(cls.img_person1_a)
        else:
            cls.ref_embedding = None

    def test_candidate_single_face_verification(self):
        if self.ref_embedding is None or not self.img_person1_b.exists():
            self.skipTest("Required test images missing")
        result = verify_candidate(self.ref_embedding, self.img_person1_b)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["faces_detected"], 1)
        self.assertIsInstance(result["best_similarity"], float)
        self.assertGreater(result["best_similarity"], 0.70)

    def test_candidate_multiple_faces_verification(self):
        if self.ref_embedding is None or not self.img_two_faces.exists():
            self.skipTest("Required test images missing")
        result = verify_candidate(self.ref_embedding, self.img_two_faces)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["faces_detected"], 2)
        self.assertEqual(result["best_similarity"], max(result["face_similarities"]))

    def test_candidate_zero_faces_handled(self):
        if self.ref_embedding is None or not self.img_no_face.exists():
            self.skipTest("Required test images missing")
        result = verify_candidate(self.ref_embedding, self.img_no_face)
        self.assertEqual(result["status"], "no_face")
        self.assertEqual(result["faces_detected"], 0)
        self.assertIsNone(result["best_similarity"])

    def test_candidate_missing_image_handled(self):
        if self.ref_embedding is None:
            self.skipTest("Reference embedding missing")
        result = verify_candidate(self.ref_embedding, "data/test_faces/non_existent.jpg")
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["error"])


if __name__ == "__main__":
    unittest.main()
