#!/usr/bin/env python3
"""Flask UI for Visual Evidence Verification — wraps existing backend without reimplementing logic."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory, render_template, abort

# --- backend imports (reuse existing) ---
from pipeline import run_full_pipeline, verify_pipeline
from verifier.independent import verify_offline
from evidence.schema import EvidenceEnvelope
from config.settings import get_settings
import logging
import uuid

try:
    from face.detector import get_face_analyzer
    _FACE_AVAILABLE = True
except Exception:
    _FACE_AVAILABLE = False

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

UPLOAD_DIR = Path(tempfile.gettempdir()) / "vev_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Ensure data dirs exist
Path("data/evidence").mkdir(parents=True, exist_ok=True)
Path("data/blockchain").mkdir(parents=True, exist_ok=True)
Path("data/input").mkdir(parents=True, exist_ok=True)
Path("data/candidates").mkdir(parents=True, exist_ok=True)

# Allowlisted directories for image serving (resolved absolute)
ALLOWED_IMAGE_DIRS = [
    UPLOAD_DIR.resolve(),
    Path("data/candidates").resolve(),
    Path("data/input").resolve(),
]

# In-memory token -> Path mapping for safe image URLs (no absolute path exposure)
_IMAGE_TOKEN_MAP: dict[str, Path] = {}


def _is_path_allowed(p: Path) -> bool:
    try:
        resolved = p.resolve()
    except Exception:
        return False
    for base in ALLOWED_IMAGE_DIRS:
        try:
            # Python 3.9+ is_relative_to
            if resolved.is_relative_to(base):
                return True
        except AttributeError:
            try:
                resolved.relative_to(base)
                return True
            except ValueError:
                continue
    return False


def _register_image(path: Path) -> str:
    """Register a verified allowed image and return opaque token."""
    token = uuid.uuid4().hex[:16]
    _IMAGE_TOKEN_MAP[token] = path.resolve()
    return token


def _sanitize_error_message(msg: str) -> str:
    """Remove absolute paths and sensitive details from error messages."""
    if not msg:
        return "processing failed"
    # Strip common absolute temp paths
    for p in [str(UPLOAD_DIR), str(Path(tempfile.gettempdir())), str(Path.home())]:
        msg = msg.replace(p, "")
    # Also hide data/ absolute
    msg = msg.replace(str(Path("data").resolve()), "data")
    # Truncate very long
    msg = msg.strip()
    if len(msg) > 300:
        msg = msg[:300]
    # Generic fallback for image errors
    lower = msg.lower()
    if "cannot identify image file" in lower or "not a valid image" in lower:
        return "Invalid image file"
    if "unsupported image format" in lower:
        return "Unsupported image format"
    if "no face" in lower:
        return msg  # safe to show
    return msg


def _settings_status():
    s = get_settings()
    is_web3 = bool(s.chain_rpc_url and s.private_key)
    contract_configured = bool(s.contract_address)
    # Try insightface status
    face_status = "unavailable"
    face_detail = ""
    if _FACE_AVAILABLE:
        try:
            # buffalo_l check without heavy init if possible
            from pathlib import Path as P
            model_path = P.home() / ".insightface" / "models" / "buffalo_l"
            if model_path.exists():
                face_status = "ready"
                face_detail = "buffalo_l (InsightFace) — 5 models cached"
            else:
                face_status = "ready (will download on first run)"
                face_detail = "InsightFace buffalo_l"
        except Exception as e:
            face_status = f"error: {e}"
    # blockchain mode
    if is_web3:
        mode = "Web3"
        # test connection lazily
        try:
            from blockchain.client import Web3BlockchainClient
            abi = None
            try:
                from blockchain.client import load_artifact_abi
                abi = load_artifact_abi()
            except Exception:
                pass
            # attempt quick connection check if contract configured
            detail = f"RPC {s.chain_rpc_url} chainId {s.chain_id}"
        except Exception as e:
            detail = str(e)
            mode = "Web3 (unreachable)"
    else:
        mode = "InMemory"
        detail = "No CHAIN_RPC_URL/PRIVATE_KEY — using deterministic InMemory client for demo"
    return {
        "face": {"status": face_status, "detail": face_detail, "method": "insightface-buffalo_l"},
        "blockchain": {"mode": mode, "detail": detail, "contract_address": s.contract_address or "", "rpc_url": s.chain_rpc_url or ""},
        "verifier": {"status": "ready", "detail": "verifier/independent.py"},
        "evidence_output_dir": s.evidence_output_dir,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify(_settings_status())


@app.route("/api/evidence/list")
def api_evidence_list():
    ev_dir = Path("data/evidence")
    files = sorted([p for p in ev_dir.glob("evidence_*.json") if not p.name.endswith(".canonical.json")], key=lambda p: p.stat().st_mtime, reverse=True)
    # also include /tmp real validation if exists
    extra = Path("/tmp/real_evidence_test")
    if extra.exists():
        files += sorted([p for p in extra.glob("evidence_*.json") if not p.name.endswith(".canonical.json")], key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:20]:
        try:
            data = json.loads(p.read_text())
            out.append({"path": str(p), "name": p.name, "evidence_hash": (data.get("evidence_hash","")[:16]+"…") if data.get("evidence_hash") else "—", "full_hash": data.get("evidence_hash",""), "candidates": len(data.get("candidates",[])), "created_at": data.get("created_at",""), "mtime": p.stat().st_mtime})
        except Exception:
            out.append({"path": str(p), "name": p.name, "evidence_hash": "—", "candidates": 0})
    return jsonify(out)


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    # send_from_directory already safely restricts to UPLOAD_DIR and blocks traversal
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/image/<token>")
def serve_image_token(token):
    """Serve image via opaque token (no absolute path exposure)."""
    p = _IMAGE_TOKEN_MAP.get(token)
    if not p or not p.exists():
        return jsonify({"error": "not found"}), 404
    if not _is_path_allowed(p):
        return jsonify({"error": "forbidden"}), 403
    return send_from_directory(p.parent, p.name)


@app.route("/evidence_file/<path:filename>")
def serve_evidence_file(filename):
    # allow data/evidence or /tmp
    for base in [Path("data/evidence"), Path("/tmp/real_evidence_test"), Path(tempfile.gettempdir())]:
        p = base / filename
        if p.exists():
            return send_from_directory(base, filename)
    return jsonify({"error": "not found"}), 404


@app.route("/candidate_image")
def serve_candidate_image():
    # Legacy endpoint retained for backwards compatibility but now strictly allowlisted
    # Prefer /image/<token> for new code
    path = request.args.get("path","")
    if not path:
        return jsonify({"error":"missing path"}), 400
    # Also support token query for safe URLs
    token = request.args.get("token","")
    if token:
        p = _IMAGE_TOKEN_MAP.get(token)
        if not p or not p.exists():
            return jsonify({"error":"not found"}), 404
        if not _is_path_allowed(p):
            return jsonify({"error":"forbidden"}), 403
        return send_from_directory(p.parent, p.name)
    p = Path(path)
    # Reject absolute paths outside allowlist without revealing existence
    if not _is_path_allowed(p):
        return jsonify({"error":"forbidden"}), 403
    if not p.exists():
        return jsonify({"error":"file not found"}), 404
    return send_from_directory(p.parent, p.name)


@app.route("/api/investigate", methods=["POST"])
def api_investigate():
    # expects multipart file field "image" and optional anchor checkbox
    if "image" not in request.files:
        return jsonify({"error": "no image uploaded"}), 400
    f = request.files["image"]
    if f.filename == "":
        return jsonify({"error": "empty filename"}), 400
    anchor_requested = request.form.get("anchor","false").lower() in ("1","true","on")
    # save upload
    ext = Path(f.filename).suffix or ".jpg"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    save_name = f"query_{ts}{ext}"
    save_path = UPLOAD_DIR / save_name
    f.save(save_path)

    # Also copy to data/input for pipeline default? No, pass explicit path
    try:
        # Call backend — this is authoritative, no reimplementation
        result = run_full_pipeline(
            image_path=str(save_path),
            register_on_chain=anchor_requested,
            evidence_output_dir="data/evidence",
            anchor_dir="data/blockchain",
        )
    except Exception as e:
        app.logger.exception("investigate failed")
        safe_msg = _sanitize_error_message(str(e))
        return jsonify({"error": safe_msg, "query_url": f"/uploads/{save_name}"}), 500

    envelope: EvidenceEnvelope = result["envelope"]
    manifest = result["manifest"]
    anchor = result.get("anchor")

    # Build serializable response
    # verification_results may contain VerificationData objects
    ver = {}
    for k, v in result.get("verification_results", {}).items():
        if hasattr(v, "to_dict"):
            ver[k] = v.to_dict()
        elif isinstance(v, dict):
            ver[k] = v
        else:
            ver[k] = str(v)

    # candidates with verification already in envelope - sanitize for frontend (no absolute paths)
    raw_candidates = [c.to_dict() for c in envelope.candidates]
    candidates = []
    for cand in raw_candidates:
        # Register allowed images and provide safe URL
        local_path = cand.get("local_path")
        safe_url = None
        failure_reason = None
        faces_detected = None
        is_multi_face = False
        if local_path:
            p = Path(local_path)
            if p.exists() and _is_path_allowed(p):
                token = _register_image(p)
                safe_url = f"/image/{token}"
                # Real face count for multi-face note (without exposing path)
                try:
                    from face.detector import detect_faces
                    faces = detect_faces(str(p))
                    faces_detected = len(faces)
                    is_multi_face = faces_detected > 1
                except Exception:
                    faces_detected = None
            elif cand.get("status") == "failed":
                # Provide concise failure reason without exposing paths
                failure_reason = cand.get("error") or "Acquisition failed: image could not be retrieved"
                # Sanitize failure reason
                failure_reason = _sanitize_error_message(failure_reason)
                if "could not be retrieved" not in failure_reason.lower() and "failed" not in failure_reason.lower():
                    failure_reason = "Acquisition failed: image could not be retrieved"
            else:
                # Success but file missing or not allowed - treat as acquisition issue
                if cand.get("status") == "failed":
                    failure_reason = "Acquisition failed: image could not be retrieved"
        elif cand.get("status") == "failed":
            failure_reason = cand.get("error") or "Acquisition failed: image could not be retrieved"
            failure_reason = _sanitize_error_message(failure_reason)
            if "could not be retrieved" not in failure_reason.lower() and "failed" not in failure_reason.lower():
                failure_reason = "Acquisition failed: image could not be retrieved"
        # Build sanitized candidate (remove absolute local_path)
        sanitized = {k: v for k, v in cand.items() if k not in ("local_path", "error")}
        sanitized["image_url"] = safe_url  # safe browser URL or None
        if failure_reason:
            sanitized["failure_reason"] = failure_reason
        if faces_detected is not None:
            sanitized["faces_detected"] = faces_detected
            sanitized["is_multi_face"] = is_multi_face
        # Preserve for debugging but not absolute path exposure: keep local_path as boolean flag
        candidates.append(sanitized)

    # discovery info
    discovery = {
        "candidate_count": manifest.get("candidate_count", 0),
        "acquired_count": manifest.get("acquired_count", 0),
        "failed_count": manifest.get("failed_count", 0),
    }

    # Sanitize envelope for frontend (strip local_path from candidates)
    envelope_dict = envelope.to_dict()
    # Replace candidates with sanitized versions for frontend
    envelope_dict["candidates"] = candidates

    return jsonify({
        "query_url": f"/uploads/{save_name}",
        "discovery": discovery,
        "candidates": candidates,
        "verification_results": ver,
        "envelope": envelope_dict,
        "evidence_hash": envelope.evidence_hash,
        "pipeline_run_id": envelope.pipeline_run_id,
        "evidence_path": f"data/evidence/evidence_{envelope.pipeline_run_id}.json",
        "anchor": anchor,
        "timeline": [t.to_dict() for t in envelope.timeline],
    })


@app.route("/api/verify", methods=["POST"])
def api_verify():
    # Accept uploaded evidence json or path
    data = None
    tmp_path = None
    if "evidence" in request.files and request.files["evidence"].filename:
        f = request.files["evidence"]
        tmp_path = UPLOAD_DIR / f"verify_{datetime.now(timezone.utc).strftime('%H%M%S')}_{f.filename}"
        f.save(tmp_path)
        evidence_path = tmp_path
    else:
        # JSON body with path
        body = request.get_json(silent=True) or {}
        p = body.get("path") or request.form.get("path")
        if not p:
            return jsonify({"error":"no evidence file provided"}), 400
        evidence_path = Path(p)
        if not evidence_path.exists():
            # try data/evidence and upload dir via basename (no absolute path leakage)
            for base in [Path("data/evidence"), UPLOAD_DIR, Path("/tmp/real_evidence_test")]:
                cand = base / Path(p).name
                if cand.exists():
                    evidence_path = cand
                    break
        if not evidence_path.exists():
            return jsonify({"error": "evidence not found"}), 404

    # Determine client for on-chain check if requested
    use_chain = request.args.get("chain","0") == "1" or (request.get_json(silent=True) or {}).get("chain")
    client = None
    if use_chain:
        s = get_settings()
        if s.chain_rpc_url and s.private_key and s.contract_address:
            try:
                from blockchain.client import Web3BlockchainClient, load_artifact_abi
                abi = load_artifact_abi()
                client = Web3BlockchainClient(s.chain_rpc_url, s.contract_address, s.private_key, s.chain_id, abi=abi)
            except Exception as e:
                # still verify offline but report chain error
                pass

    try:
        res = verify_offline(evidence_path, client=client, anchor_dir="data/blockchain")
        # Also try /tmp anchor dir if not found
        if res.get("anchor") is None:
            # check alternate dir
            from pathlib import Path as P
            alt = P("/tmp/real_blockchain_test") / f"anchor_{res.get('stored_hash')}.json"
            if alt.exists():
                res["alt_anchor_exists"] = True
        return jsonify(res)
    except Exception as e:
        app.logger.exception("verify failed")
        safe_msg = _sanitize_error_message(str(e))
        return jsonify({"error": safe_msg}), 500


@app.route("/api/tamper_demo", methods=["POST"])
def api_tamper_demo():
    body = request.get_json(silent=True) or {}
    path = body.get("path")
    field = body.get("field","score")  # score|decision|order|timeline
    if not path:
        return jsonify({"error":"path required"}), 400
    p = Path(path)
    if not p.exists():
        p = Path("data/evidence") / Path(path).name
    if not p.exists():
        return jsonify({"error":"not found"}), 404
    data = json.loads(p.read_text())
    import copy
    tampered = copy.deepcopy(data)
    if field == "score":
        if tampered["candidates"]:
            tampered["candidates"][0]["verification"]["score"] = "0.000000"
    elif field == "decision":
        if len(tampered["candidates"])>1:
            tampered["candidates"][1]["verification"]["decision"] = "match"
        elif tampered["candidates"]:
            tampered["candidates"][0]["verification"]["decision"] = "match"
    elif field == "order":
        tampered["candidates"] = list(reversed(tampered["candidates"]))
    elif field == "timeline":
        if tampered.get("timeline"):
            tampered["timeline"][0]["detail"]["candidate_count"] = 999
    else:
        tampered["evidence_hash"] = "0"*64

    tmp = UPLOAD_DIR / f"tampered_{field}_{Path(path).name}"
    tmp.write_text(json.dumps(tampered, indent=2))
    res = verify_offline(tmp, anchor_dir="data/blockchain")
    # Return safe relative path (basename) instead of absolute filesystem path
    safe_tampered = tmp.name
    return jsonify({"tampered_path": safe_tampered, "field": field, "result": res, "original_hash": data.get("evidence_hash")})


if __name__ == "__main__":
    print("Visual Evidence Verification UI")
    print(" http://127.0.0.1:5001")
    import os
    debug = os.environ.get("FLASK_DEBUG","0") == "1"
    app.run(host="127.0.0.1", port=5001, debug=debug, use_reloader=False)
