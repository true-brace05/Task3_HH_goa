import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

# Global singleton face analyzer to avoid reloading heavy model on every call
_ANALYZER: Optional[FaceAnalysis] = None


def get_face_analyzer(model_name: str = "buffalo_l", det_size: tuple = (640, 640)) -> FaceAnalysis:
    """Initialize or retrieve the cached InsightFace FaceAnalysis instance."""
    global _ANALYZER
    if _ANALYZER is None:
        logger.info("Initializing InsightFace '%s' on CPU...", model_name)
        app = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=det_size)
        _ANALYZER = app
        logger.info("InsightFace '%s' ready.", model_name)
    return _ANALYZER


def _load_image(image_path: str | Path) -> np.ndarray:
    """Validate and load image into BGR format using OpenCV."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {image_path}")

    # Read image using OpenCV (supports Unicode paths on Windows via numpy fromfile if needed)
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not decode image or unsupported format: {image_path}")
    return img


def detect_faces(image_path: str | Path) -> List[Dict[str, Any]]:
    """
    Detect all faces in an image.
    
    Returns a list of dicts for each face containing:
    - 'bbox': [x1, y1, x2, y2]
    - 'det_score': float detection confidence
    - 'embedding': raw face embedding vector (numpy array)
    - 'kps': facial keypoints
    """
    img = _load_image(image_path)
    app = get_face_analyzer()
    raw_faces = app.get(img)

    faces = []
    for face in raw_faces:
        faces.append({
            "bbox": face.bbox.tolist() if hasattr(face, "bbox") and face.bbox is not None else [],
            "det_score": float(face.det_score) if hasattr(face, "det_score") and face.det_score is not None else 0.0,
            "embedding": face.embedding if hasattr(face, "embedding") and face.embedding is not None else None,
            "kps": face.kps.tolist() if hasattr(face, "kps") and face.kps is not None else [],
        })
    return faces


def detect_query_face(image_path: str | Path) -> Dict[str, Any]:
    """
    Validate and detect face in a reference/query image.
    
    Enforces MVP query requirements:
    - 0 faces detected  -> raises ValueError
    - >1 faces detected -> raises ValueError
    - exactly 1 face    -> returns face dictionary
    """
    faces = detect_faces(image_path)
    face_count = len(faces)

    if face_count == 0:
        raise ValueError(f"No face detected in query image: {image_path}")
    elif face_count > 1:
        raise ValueError(
            f"Multiple faces ({face_count}) detected in query image: {image_path}. "
            "Exactly one clear face is required for query images."
        )

    return faces[0]
