"""
Face Verification Pipeline Module.

Integrates:
1. Reference query face detection & validation (strictly 1 face).
2. Reference face embedding generation.
3. Candidate discovery & acquisition via Nikhil's search module.
4. Face verification on acquired candidate images.
5. Candidate ranking (highest similarity first) and 3-state decision classification.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from face.detector import detect_query_face
from face.embedder import generate_embedding
from face.matcher import verify_candidate
from face.ranking import rank_candidates, make_decision, DEFAULT_HIGH_THRESHOLD, DEFAULT_LOW_THRESHOLD

logger = logging.getLogger(__name__)


def run_face_pipeline(
    reference_image_path: Union[str, Path],
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
    discovery_manifest: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = "data/debug/verification_results.json",
) -> Dict[str, Any]:
    """
    Execute the integrated face verification pipeline on a reference image.
    
    Flow:
    1. Validate reference image (strictly 1 face).
    2. Generate reference face embedding vector (512-dim).
    3. Run candidate discovery & acquisition (or use provided discovery_manifest).
    4. Verify each acquired candidate image against reference embedding.
    5. Rank all candidates by similarity and assign decisions (MATCH / NO MATCH / INCONCLUSIVE).
    6. Automatically save output to data/debug/verification_results.json.
    
    Returns:
        Structured pipeline results dict containing query info, discovery counts,
        thresholds, and ranked candidates with complete discovery & face metadata.
    """
    ref_path = Path(reference_image_path)
    if not ref_path.exists() or not ref_path.is_file():
        raise FileNotFoundError(f"Reference image not found: {reference_image_path}")

    logger.info("[PIPELINE] Validating reference image: %s", ref_path.name)

    # 1. Validate query image (strictly 1 face)
    query_face = detect_query_face(ref_path)
    query_embedding = generate_embedding(query_face)
    logger.info("[PIPELINE] Reference face validated (det_score: %.4f)", query_face.get("det_score", 0.0))

    # 2. Candidate Discovery + Acquisition
    if discovery_manifest is None:
        logger.info("[PIPELINE] Running discovery & candidate acquisition...")
        try:
            from search.acquisition.runner import run_pipeline as run_discovery_pipeline
            discovery_manifest = run_discovery_pipeline(str(ref_path))
        except Exception as e:
            logger.error("[PIPELINE] Discovery failed: %s", e)
            discovery_manifest = {
                "query_image": str(ref_path),
                "candidate_count": 0,
                "acquired_count": 0,
                "failed_count": 0,
                "candidates": [],
                "error": str(e),
            }

    raw_candidates: List[Dict[str, Any]] = discovery_manifest.get("candidates", [])
    logger.info("[PIPELINE] Discovered %d candidates, processing verification...", len(raw_candidates))

    # 3. Verify each candidate
    verified_candidates = []
    verified_count = 0

    for cand in raw_candidates:
        cand_record = dict(cand)  # copy to preserve all discovery metadata
        status = cand_record.get("status")
        local_path_str = cand_record.get("local_path")

        # Only attempt face verification on successfully acquired candidates with existing local files
        if status == "success" and local_path_str and Path(local_path_str).exists():
            try:
                ver_result = verify_candidate(query_embedding, local_path_str)
                cand_record["faces_detected"] = ver_result.get("faces_detected", 0)
                cand_record["best_face_index"] = ver_result.get("best_face_index")
                cand_record["similarity"] = ver_result.get("best_similarity")
                cand_record["best_similarity"] = ver_result.get("best_similarity")
                cand_record["face_similarities"] = ver_result.get("face_similarities", [])
                cand_record["quality_status"] = ver_result.get("quality_status", "GOOD")
                cand_record["verification_status"] = ver_result.get("status", "success")
                if ver_result.get("status") == "success":
                    verified_count += 1
            except Exception as e:
                logger.warning("[PIPELINE] Face verification failed for %s: %s", cand_record.get("candidate_id"), e)
                cand_record["faces_detected"] = 0
                cand_record["best_face_index"] = None
                cand_record["similarity"] = None
                cand_record["best_similarity"] = None
                cand_record["face_similarities"] = []
                cand_record["quality_status"] = "ERROR"
                cand_record["verification_status"] = "error"
                cand_record["error"] = f"Face verification error: {e}"
        else:
            # Candidate was not acquired or missing file -> safe inconclusive handling
            cand_record["faces_detected"] = 0
            cand_record["best_face_index"] = None
            cand_record["similarity"] = None
            cand_record["best_similarity"] = None
            cand_record["face_similarities"] = []
            cand_record["quality_status"] = "ACQUISITION_FAILED" if status == "failed" else "UNAVAILABLE"
            cand_record["verification_status"] = "skipped"

        verified_candidates.append(cand_record)

    # 4. Rank candidates descending by similarity and assign decision states
    ranked = rank_candidates(verified_candidates, high_threshold=high_threshold, low_threshold=low_threshold)

    result_manifest = {
        "query_image": str(ref_path),
        "reference_face_detected": True,
        "detection_confidence": query_face.get("det_score"),
        "embedding_dimension": len(query_embedding),
        "candidates_discovered": discovery_manifest.get("candidate_count", len(raw_candidates)),
        "candidates_acquired": discovery_manifest.get("acquired_count", sum(1 for c in raw_candidates if c.get("status") == "success")),
        "candidates_verified": verified_count,
        "high_threshold": high_threshold,
        "low_threshold": low_threshold,
        "threshold_notice": "DEMO ONLY - NOT CALIBRATED PRODUCTION THRESHOLDS",
        "ranked_candidates": ranked,
    }

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result_manifest, f, indent=2)
        logger.info("[PIPELINE] Verification results saved to: %s", out_file)

    return result_manifest


def main():
    parser = argparse.ArgumentParser(description="End-to-End Face Verification Pipeline")
    parser.add_argument(
        "--image",
        default="data/test_faces/person1_a.jpg",
        help="Path to query reference image (default: data/test_faces/person1_a.jpg)",
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

    print("=" * 70)
    print("INTEGRATED FACE VERIFICATION PIPELINE (STEP 4)")
    print("=" * 70)
    print(f"Reference Image : {args.image}")
    print(f"High Threshold  : {args.high:.2f} (DEMO ONLY)")
    print(f"Low Threshold   : {args.low:.2f} (DEMO ONLY)")
    print("-" * 70)

    try:
        manifest = run_face_pipeline(args.image, high_threshold=args.high, low_threshold=args.low)
    except Exception as e:
        print(f"\n[PIPELINE FAILED] Reason: {e}")
        return

    print(f"\nReference face        : DETECTED (Confidence: {manifest['detection_confidence']:.4f})")
    print(f"Candidates discovered : {manifest['candidates_discovered']}")
    print(f"Candidates acquired   : {manifest['candidates_acquired']}")
    print(f"Candidates verified   : {manifest['candidates_verified']}")

    print("\n" + "=" * 70)
    print("RANKED CANDIDATES")
    print("=" * 70)

    if not manifest["ranked_candidates"]:
        print("No candidates discovered or verified.")
    else:
        for cand in manifest["ranked_candidates"]:
            sim_val = cand.get("similarity")
            sim_str = f"{sim_val:.6f}" if sim_val is not None else "None"
            print(f"Rank {cand.get('rank')}:")
            print(f"  Candidate ID : {cand.get('candidate_id')}")
            print(f"  Similarity   : {sim_str}")
            print(f"  Decision     : {cand.get('decision')}")
            print(f"  Faces found  : {cand.get('faces_detected', 0)}")
            print(f"  Source URL   : {cand.get('source_url')}")
            print(f"  Local Path   : {cand.get('local_path')}")
            print(f"  Provider     : {cand.get('discovery_provider', cand.get('provider'))}")
            print("-" * 40)
    print("=" * 70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
