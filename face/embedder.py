import logging
from pathlib import Path
from typing import Union, Dict, Any

import numpy as np

from face.detector import detect_query_face

logger = logging.getLogger(__name__)


def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    """
    L2-normalize a face embedding vector to unit length.
    
    Cosine similarity between two unit vectors is simply their dot product.
    """
    if embedding is None or not isinstance(embedding, np.ndarray):
        raise ValueError("Invalid embedding: expected a numpy ndarray.")

    emb = embedding.astype(np.float32).flatten()
    norm = np.linalg.norm(emb)
    if norm == 0 or np.isnan(norm):
        raise ValueError("Cannot normalize zero-vector or NaN embedding.")
    return emb / norm


def generate_embedding(face_or_image: Union[Dict[str, Any], str, Path, np.ndarray]) -> np.ndarray:
    """
    Extract and return an L2-normalized face embedding vector.
    
    Accepts:
    - A face dictionary returned by detect_query_face / detect_faces
    - A file path to a single-face image (will run detect_query_face automatically)
    - An existing numpy embedding array
    """
    if isinstance(face_or_image, dict):
        raw_emb = face_or_image.get("embedding")
        if raw_emb is None:
            raise ValueError("Face dictionary does not contain an 'embedding' key.")
        return normalize_embedding(raw_emb)

    elif isinstance(face_or_image, (str, Path)):
        face_info = detect_query_face(face_or_image)
        return normalize_embedding(face_info["embedding"])

    elif isinstance(face_or_image, np.ndarray):
        return normalize_embedding(face_or_image)

    else:
        raise TypeError(f"Unsupported input type for generate_embedding: {type(face_or_image)}")


# plan.pdf-compatible alias
generate_query_embedding = generate_embedding

