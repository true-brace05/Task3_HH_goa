"""Canonical JSON serialization for deterministic hashing.

Spec:
- sort dict keys deterministically
- preserve list order
- separators (',', ':')
- ensure_ascii=False, UTF-8, no trailing newline
- None -> null
- reject floats anywhere (recursively) with ValueError
"""

from __future__ import annotations

import json
from typing import Any


def _reject_floats(obj: Any) -> None:
    """Recursively reject float values."""
    if isinstance(obj, float):
        raise ValueError(f"float values are not allowed in canonical JSON: {obj!r}")
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _reject_floats(item)
    # other types (str, int, bool, None) are fine
    # Note: bool is subclass of int in Python, but json handles it correctly;
    # we do not reject booleans.


def canonical_dumps(obj: Any) -> bytes:
    """Serialize obj to canonical JSON bytes.

    Deterministic: same logical data always produces identical bytes.

    Raises:
        ValueError: if obj contains float anywhere.
    """
    _reject_floats(obj)
    # json.dumps with sort_keys, separators, ensure_ascii=False is deterministic
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")
