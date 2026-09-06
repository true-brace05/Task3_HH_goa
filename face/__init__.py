"""Face verification package for Task3_HH_goa."""

from face.detector import detect_faces, detect_query_face, get_face_analyzer
from face.embedder import generate_embedding, generate_query_embedding, normalize_embedding
from face.matcher import compute_similarity, verify_candidate, verify_candidate_embeddings
from face.ranking import make_decision, rank_candidates
from face.pipeline import run_face_pipeline

__all__ = [
    "detect_faces",
    "detect_query_face",
    "get_face_analyzer",
    "generate_embedding",
    "generate_query_embedding",
    "normalize_embedding",
    "compute_similarity",
    "verify_candidate",
    "verify_candidate_embeddings",
    "make_decision",
    "rank_candidates",
    "run_face_pipeline",
]
