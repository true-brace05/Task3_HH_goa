"""
Candidate ranking and decision classification module.

Provides:
- make_decision(): maps a similarity score to MATCH, NO MATCH, or INCONCLUSIVE using configurable thresholds.
- rank_candidates(): sorts candidate verification results descending by similarity and assigns ranks.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Temporary / Demo thresholds (Explicitly NOT scientifically validated production thresholds)
DEFAULT_HIGH_THRESHOLD = 0.70
DEFAULT_LOW_THRESHOLD = 0.40


def make_decision(
    similarity: Optional[float],
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
) -> str:
    """
    Classify a similarity score into a decision state.
    
    Decision States:
    - MATCH        : similarity >= high_threshold (strong facial feature match)
    - NO MATCH     : similarity <= low_threshold (distinct facial features)
    - INCONCLUSIVE : low_threshold < similarity < high_threshold OR similarity is None
    
    Boundary Behavior:
    - similarity == high_threshold -> "MATCH"
    - similarity == low_threshold  -> "NO MATCH"
    - similarity is None           -> "INCONCLUSIVE"
    
    Note:
    These thresholds are for DEMO / POC purposes and must be calibrated on
    authorized evaluation datasets.
    """
    if low_threshold > high_threshold:
        raise ValueError(
            f"Invalid threshold configuration: low_threshold ({low_threshold}) "
            f"cannot be greater than high_threshold ({high_threshold})"
        )

    if similarity is None:
        return "INCONCLUSIVE"

    sim = float(similarity)
    if sim >= high_threshold:
        return "MATCH"
    elif sim <= low_threshold:
        return "NO MATCH"
    else:
        return "INCONCLUSIVE"


def rank_candidates(
    candidates: List[Dict[str, Any]],
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    Sort candidate verification results in descending order of similarity and assign 1-indexed ranks.
    
    Handles:
    - Normal candidates with numeric similarity (sorted highest first).
    - Candidates with missing/None similarity (placed at the bottom safely).
    - Preservation of candidate_id (generates fallback 'cand_001', etc. if missing).
    - Automatic decision calculation for each candidate.
    
    Returns:
        List of ranked candidate dictionaries containing at least:
        - candidate_id (str)
        - rank (int, 1-indexed)
        - similarity (Optional[float])
        - decision (str: "MATCH", "NO MATCH", "INCONCLUSIVE")
        - (and all other original candidate attributes)
    """
    if not candidates:
        return []

    # Helper function for sorting: items with None similarity go to the end (-infinity)
    def sort_key(cand: Dict[str, Any]) -> float:
        sim = cand.get("best_similarity", cand.get("similarity"))
        if sim is None:
            return float("-inf")
        try:
            return float(sim)
        except (ValueError, TypeError):
            return float("-inf")

    # Sort descending by similarity score
    sorted_candidates = sorted(candidates, key=sort_key, reverse=True)

    ranked_results = []
    for rank_idx, cand in enumerate(sorted_candidates, start=1):
        item = dict(cand)  # Shallow copy to preserve original dict
        
        # Resolve similarity
        sim = item.get("best_similarity", item.get("similarity"))
        if sim is not None:
            try:
                sim = float(sim)
            except (ValueError, TypeError):
                sim = None
        item["similarity"] = sim

        # Preserve or generate candidate_id
        candidate_id = item.get("candidate_id")
        if not candidate_id:
            candidate_id = f"cand_{rank_idx:03d}"
        item["candidate_id"] = candidate_id

        # Assign rank (1-indexed)
        item["rank"] = rank_idx

        # Assign decision if not already present
        if "decision" not in item or item["decision"] is None:
            item["decision"] = make_decision(sim, high_threshold=high_threshold, low_threshold=low_threshold)

        ranked_results.append(item)

    return ranked_results
