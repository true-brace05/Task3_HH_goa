import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import numpy as np

from face.embedder import normalize_embedding, generate_embedding
from face.detector import detect_faces

logger = logging.getLogger(__name__)


def compute_similarity(embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
    """
    Calculate the cosine similarity between two face embeddings.
    
    Cosine similarity is defined as: (A · B) / (||A|| * ||B||)
    
    Returns:
        float: A numeric scalar value in the range [-1.0, 1.0].
        (Higher values indicate higher facial feature similarity).
    
    Note:
        Cosine similarity is a geometric similarity metric in embedding space,
        NOT a probability and NOT a percentage.
    """
    if embedding_a is None or embedding_b is None:
        raise ValueError("Embeddings cannot be None.")

    # Normalize both vectors to unit length
    vec_a = normalize_embedding(embedding_a)
    vec_b = normalize_embedding(embedding_b)

    if vec_a.shape != vec_b.shape:
        raise ValueError(
            f"Embedding shape mismatch: vec_a shape {vec_a.shape} vs vec_b shape {vec_b.shape}"
        )

    # Dot product of unit vectors equals cosine similarity
    similarity = float(np.dot(vec_a, vec_b))

    # Numerical clip to strictly [-1.0, 1.0] to prevent slight float precision overflow
    clipped_similarity = max(-1.0, min(1.0, similarity))
    return clipped_similarity


def verify_candidate_embeddings(
    reference_embedding: np.ndarray,
    candidate_embeddings: List[np.ndarray],
) -> Dict[str, Any]:
    """
    Compare a reference embedding against a list of candidate face embeddings.
    
    Calculates similarity with EVERY face embedding and selects the MAXIMUM similarity.
    (Does not average the similarities).
    
    Returns:
        dict: {
            "faces_detected": int,
            "best_face_index": Optional[int],  # 0-indexed
            "best_similarity": Optional[float],
            "face_similarities": List[float],
            "status": str,
            "quality_status": str,
            "error": Optional[str],
        }
    """
    if reference_embedding is None:
        raise ValueError("reference_embedding cannot be None.")

    face_count = len(candidate_embeddings)
    if face_count == 0:
        return {
            "faces_detected": 0,
            "best_face_index": None,
            "best_similarity": None,
            "face_similarities": [],
            "status": "no_face",
            "quality_status": "NO_FACE",
            "error": "No candidate face embeddings provided.",
        }

    similarities: List[float] = []
    best_sim: float = -1.0
    best_idx: int = 0

    for idx, cand_emb in enumerate(candidate_embeddings):
        sim = compute_similarity(reference_embedding, cand_emb)
        similarities.append(sim)
        if sim > best_sim:
            best_sim = sim
            best_idx = idx

    return {
        "faces_detected": face_count,
        "best_face_index": best_idx,
        "best_similarity": best_sim,
        "face_similarities": similarities,
        "status": "success",
        "quality_status": "GOOD",
        "error": None,
    }


def verify_candidate(
    reference_embedding: np.ndarray,
    candidate_image: Union[str, Path],
) -> Dict[str, Any]:
    """
    Verify a candidate image against a reference face embedding.
    
    Handles:
    - Candidate with 0 faces: returns clear no_face status without crashing.
    - Candidate with 1 face: generates embedding and computes similarity.
    - Candidate with multiple faces: computes similarity for each face and selects MAX.
    
    Returns:
        dict containing faces_detected, best_face_index, best_similarity,
        face_similarities, status, quality_status, and error.
    """
    cand_path = Path(candidate_image)
    if not cand_path.exists() or not cand_path.is_file():
        return {
            "faces_detected": 0,
            "best_face_index": None,
            "best_similarity": None,
            "face_similarities": [],
            "status": "error",
            "quality_status": "ERROR",
            "error": f"Candidate image not found: {candidate_image}",
        }

    try:
        detected_faces = detect_faces(cand_path)
    except Exception as e:
        return {
            "faces_detected": 0,
            "best_face_index": None,
            "best_similarity": None,
            "face_similarities": [],
            "status": "error",
            "quality_status": "ERROR",
            "error": f"Failed to detect faces in candidate image: {e}",
        }

    if len(detected_faces) == 0:
        return {
            "faces_detected": 0,
            "best_face_index": None,
            "best_similarity": None,
            "face_similarities": [],
            "status": "no_face",
            "quality_status": "NO_FACE",
            "error": f"No face detected in candidate image: {cand_path.name}",
        }

    # Extract embeddings for all detected faces
    cand_embeddings = []
    for face in detected_faces:
        cand_embeddings.append(generate_embedding(face))

    return verify_candidate_embeddings(reference_embedding, cand_embeddings)
