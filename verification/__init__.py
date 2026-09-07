"""Face verification adapter package.

Member 1 real implementation (InsightFace buffalo_l) via face/ module.
Thin adapter converts face results to VerificationData contract.
"""

from verification.adapter import verify_candidate, verify_candidates, format_score

__all__ = ["verify_candidate", "verify_candidates", "format_score"]
