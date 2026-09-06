"""
Face Verification Proof-of-Concept (POC) Runner — Step 3.

Demonstrates:
1. Validating reference face image (enforces exactly 1 face).
2. Generating normalized reference embedding.
3. Evaluating candidate images (single-face, multi-face, different person, no-face).
4. Ranking candidate verification results in descending order of similarity.
5. Classifying results into 3 decision states (MATCH, NO MATCH, INCONCLUSIVE) using demo thresholds.
6. Clearly displaying uncalibrated demo threshold notices.
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

from face.detector import detect_query_face
from face.embedder import generate_embedding
from face.matcher import verify_candidate
from face.ranking import rank_candidates, make_decision, DEFAULT_HIGH_THRESHOLD, DEFAULT_LOW_THRESHOLD


def run_face_poc(
    reference_path: str,
    candidate_paths: List[str],
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Run face verification and ranking POC on a reference image and candidate images."""
    ref_file = Path(reference_path)

    print("=" * 65)
    print("FACE VERIFICATION & RANKING POC — RUNNER (STEP 3)")
    print("=" * 65)
    print(f"Reference Image : {ref_file}")
    print("-" * 65)

    # 1. Detect and validate reference/query face (must be exactly 1 face)
    try:
        ref_face = detect_query_face(ref_file)
        print("Reference face detected : YES (exactly 1 face accepted)")
        print(f"  Detection confidence  : {ref_face['det_score']:.4f}")
        print(f"  Bounding box [x1,y1,x2,y2]: {[round(x, 1) for x in ref_face['bbox']]}")
    except Exception as e:
        print(f"Reference face detected : NO / REJECTED ({e})")
        return []

    # 2. Generate reference embedding
    ref_embedding = generate_embedding(ref_face)
    print(f"Reference embedding shape : {ref_embedding.shape} (dimension: {len(ref_embedding)})")

    # Print Demo Threshold Notice
    print("\n" + "-" * 65)
    print("TEMPORARY DEMO THRESHOLDS (DEMO ONLY — NOT CALIBRATED PRODUCTION THRESHOLDS)")
    print(f"  HIGH_THRESHOLD = {high_threshold:.2f}  (Score >= {high_threshold:.2f} -> MATCH)")
    print(f"  LOW_THRESHOLD  = {low_threshold:.2f}  (Score <= {low_threshold:.2f} -> NO MATCH)")
    print("  BETWEEN THRESHOLDS / NO-FACE -> INCONCLUSIVE")
    print("  Note: Final thresholds must be calibrated on authorized test datasets.")
    print("-" * 65)

    # 3. Verify each candidate image
    raw_results = []
    for idx, cand_path_str in enumerate(candidate_paths, start=1):
        cand_path = Path(cand_path_str)
        cand_id = f"cand_{idx:03d}"
        
        ver_result = verify_candidate(ref_embedding, cand_path)
        ver_result["candidate_id"] = cand_id
        ver_result["candidate_path"] = str(cand_path)
        raw_results.append(ver_result)

        sim_str = f"{ver_result['best_similarity']:.6f}" if ver_result['best_similarity'] is not None else "None"
        cand_decision = make_decision(ver_result['best_similarity'], high_threshold, low_threshold)
        ver_result["decision"] = cand_decision

        print(f"\nCandidate {cand_id} ({cand_path.name}):")
        print(f"  Faces detected   : {ver_result['faces_detected']}")
        if ver_result['face_similarities']:
            for f_idx, f_sim in enumerate(ver_result['face_similarities']):
                print(f"    Face {f_idx} similarity: {f_sim:.6f}")
        print(f"  Best similarity  : {sim_str}")
        print(f"  Decision         : {cand_decision}")

    # 4. Rank candidates descending by similarity
    ranked = rank_candidates(raw_results, high_threshold=high_threshold, low_threshold=low_threshold)

    print("\n" + "=" * 65)
    print("RANKED CANDIDATES (Highest Similarity First)")
    print("=" * 65)
    for cand in ranked:
        sim_val = cand.get("similarity")
        sim_display = f"{sim_val:.6f}" if sim_val is not None else "None (No Face)"
        print(
            f"Rank {cand['rank']}: [{cand['candidate_id']}] "
            f"{Path(cand.get('candidate_path', '')).name:<14} -> "
            f"Similarity: {sim_display:<15} -> Decision: {cand['decision']}"
        )
    print("=" * 65)

    return ranked


def main():
    parser = argparse.ArgumentParser(description="Face Verification POC — Step 3 (Ranking & Decision)")
    parser.add_argument(
        "--ref",
        default="data/test_faces/person1_a.jpg",
        help="Path to reference face image",
    )
    parser.add_argument(
        "--cands",
        nargs="*",
        default=[
            "data/test_faces/person1_b.jpg",
            "data/test_faces/two_faces.jpg",
            "data/test_faces/person2_a.jpg",
            "data/test_faces/no_face.jpg",
        ],
        help="Paths to candidate face images",
    )
    parser.add_argument(
        "--high",
        type=float,
        default=DEFAULT_HIGH_THRESHOLD,
        help="Temporary demo HIGH threshold",
    )
    parser.add_argument(
        "--low",
        type=float,
        default=DEFAULT_LOW_THRESHOLD,
        help="Temporary demo LOW threshold",
    )
    args = parser.parse_args()

    run_face_poc(args.ref, args.cands, high_threshold=args.high, low_threshold=args.low)


if __name__ == "__main__":
    main()
