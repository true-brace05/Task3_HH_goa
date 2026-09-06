"""Face verification adapter package.

Member 1 implementation is currently a stub (no real model committed).
This adapter provides a stable deterministic contract for pipeline integration
and can be replaced with a real model without changing evidence hashing.
"""

from verification.adapter import verify_candidate, verify_candidates, format_score

__all__ = ["verify_candidate", "verify_candidates", "format_score"]
