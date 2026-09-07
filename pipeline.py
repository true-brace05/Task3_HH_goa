"""Root pipeline — Discovery → Acquisition → Face Verification → Evidence → Blockchain (Phase 4).

Flow: Query Image → Discovery → Normalization → Acquisition → Face Verification
      → Evidence Builder (candidate hashes) → Root Hash → Blockchain Anchor

Immutability:
- EvidenceEnvelope hashed with pre-registration timeline only (including verification_complete, evidence_built)
- blockchain_registered stays outside envelope, in EventBus + anchor file
- verification results are inside candidate evidence before hashing
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evidence.builder import build_evidence
from evidence.timeline import create_timeline_event
from utils.events import EventBus
from blockchain.registration import register_evidence
from blockchain.client import BlockchainClient, InMemoryBlockchainClient
from verifier.independent import verify_offline
import logging

logger = logging.getLogger(__name__)


def _get_default_client() -> BlockchainClient:
    """Return InMemory or Web3 client based on config.

    For CI/tests, defaults to InMemory when CHAIN_RPC_URL not set.
    """
    try:
        from config.settings import get_settings
        settings = get_settings()
        if settings.chain_rpc_url and settings.private_key:
            # Try Web3 if configured and available
            try:
                from blockchain.client import Web3BlockchainClient, load_artifact_abi
                abi = load_artifact_abi()
                # Only use Web3 if ABI is available and contract configured
                if abi is not None and settings.contract_address:
                    return Web3BlockchainClient(
                        rpc_url=settings.chain_rpc_url,
                        contract_address=settings.contract_address,
                        private_key=settings.private_key,
                        chain_id=settings.chain_id,
                        abi=abi,
                    )
                # ABI missing or no contract -> fall back to InMemory (simulated)
                logger.info("Web3 config present but ABI/contract missing — using InMemory anchor")
                return InMemoryBlockchainClient(contract_address=settings.contract_address or "0x0000000000000000000000000000000000000000")
            except Exception as e:
                logger.warning("Web3 init failed, falling back to InMemory: %s", e)
                pass
        return InMemoryBlockchainClient(contract_address=settings.contract_address or "0x0000000000000000000000000000000000000000")
    except Exception:
        return InMemoryBlockchainClient()

def _is_inmemory_client(client: BlockchainClient) -> bool:
    """Check if client is InMemory (simulated) vs Web3 (real chain)."""
    from blockchain.client import InMemoryBlockchainClient as IMC
    return isinstance(client, IMC)


def _run_face_verification(manifest: dict, query_image: str) -> dict:
    """Run face verification for acquired candidates, return enriched manifest.

    One failed candidate verification must NOT crash pipeline.
    Generates query face embedding ONCE then reuses for all candidates
    (requirement: do not recompute query embedding per candidate).
    Returns new manifest with verification results attached to each candidate.
    Also returns verification_results mapping for pipeline return.
    """
    try:
        from verification.adapter import (
            get_reference_embedding,
            verify_candidate_with_embedding,
            METHOD as VERIF_METHOD,
        )
        from verification.adapter import verify_candidate as _verify_single  # fallback
    except ImportError:
        # No verification module — return manifest unchanged with pending verification
        return manifest, {}

    enriched = dict(manifest)
    candidates = list(manifest.get("candidates", []))
    verification_results = {}
    new_candidates = []

    # Collect candidates that need verification (to avoid computing embedding if none)
    needs_verification = [
        c for c in candidates if (c.get("status") or c.get("retrieval_status")) == "success" and c.get("local_path")
    ]

    reference_embedding = None
    query_error = None
    query_face_detected: Optional[bool] = None

    if needs_verification:
        try:
            reference_embedding, _face_info = get_reference_embedding(query_image)
            query_face_detected = True
        except Exception as e:
            query_error = str(e)
            # Determine if query had no face vs multiple vs missing
            msg = str(e).lower()
            is_no_face = "no face" in msg or "no face detected" in msg
            query_face_detected = False if is_no_face else None
            reference_embedding = None

    for cand in candidates:
        status = cand.get("status") or cand.get("retrieval_status")
        local_path = cand.get("local_path")
        cid = cand.get("candidate_id", "unknown")
        # Only verify successfully acquired with usable local_path
        if status != "success" or not local_path:
            # keep failed/non-usable as is (verification remains pending)
            # Ensure verification field exists for evidence builder
            if "verification" not in cand:
                cand = dict(cand)
                cand["verification"] = {
                    "method": "pending",
                    "score": None,
                    "decision": None,
                    "timestamp": None,
                    "query_face_detected": None,
                    "candidate_face_detected": None,
                    "error": None,
                }
            new_candidates.append(cand)
            continue

        # If query embedding failed, produce error/inconclusive for all remaining
        if reference_embedding is None:
            from evidence.schema import VerificationData

            is_no_face = query_face_detected is False
            decision = "inconclusive" if is_no_face else "error"
            err_result = VerificationData(
                method=VERIF_METHOD,
                score=None,
                decision=decision,
                timestamp=datetime.now(timezone.utc).isoformat(),
                query_face_detected=query_face_detected,
                candidate_face_detected=None,
                error=query_error or "query face embedding failed",
            )
            verification_results[cid] = err_result
            cand = dict(cand)
            cand["verification"] = err_result.to_dict()
            new_candidates.append(cand)
            continue

        try:
            result = verify_candidate_with_embedding(reference_embedding, local_path)
            verification_results[cid] = result
            cand = dict(cand)
            cand["verification"] = result.to_dict()
        except Exception as e:
            # Unexpected error → structured error result, continue
            from evidence.schema import VerificationData

            err_result = VerificationData(
                method=VERIF_METHOD,
                score=None,
                decision="error",
                timestamp=datetime.now(timezone.utc).isoformat(),
                query_face_detected=query_face_detected,
                candidate_face_detected=None,
                error=str(e),
            )
            verification_results[cid] = err_result
            cand = dict(cand)
            cand["verification"] = err_result.to_dict()
        new_candidates.append(cand)
    enriched["candidates"] = new_candidates
    return enriched, verification_results


def run_full_pipeline(
    image_path: str = "data/input/query.jpg",
    register_on_chain: bool = True,
    blockchain_client: Optional[BlockchainClient] = None,
    evidence_output_dir: str = "data/evidence",
    anchor_dir: str = "data/blockchain",
):
    """Run Discovery → Face Verification → Evidence → (optional) Blockchain.

    Discovery interface is search.acquisition.runner.run_pipeline (real).
    Face verification MUST happen before evidence hashing.
    """
    # Lazy import discovery to keep evidence/blockchain independent
    from search.acquisition.runner import run_pipeline as run_discovery_pipeline

    # 1. Discovery/Acquisition → manifest (single execution per pipeline run)
    manifest = run_discovery_pipeline(image_path)
    # Auditable logging: discovery -> acquisition counts
    logger.info("AUDIT DISCOVERED: %s", manifest.get("candidate_count", 0))
    logger.info("AUDIT NORMALIZED: %s", manifest.get("candidate_count", 0))  # normalizer preserves count after dedupe; manifest reflects normalized
    logger.info("AUDIT ACQUIRED: %s", manifest.get("acquired_count", 0))
    logger.info("AUDIT FAILED: %s", manifest.get("failed_count", 0))

    # 2. Face verification (before hashing) — attach results to manifest
    enriched_manifest, verification_results = _run_face_verification(manifest, image_path)
    logger.info("AUDIT PASSED TO VERIFICATION: %s", len(verification_results))
    logger.info("AUDIT INCLUDED IN EVIDENCE: %s candidates (acquired %s)", len(enriched_manifest.get("candidates", [])), enriched_manifest.get("acquired_count", manifest.get("acquired_count", 0)))

    # 3. Construct pre-registration timeline (only these go into hashed envelope)
    #    Includes verification_complete before evidence_built
    ts_base = manifest.get("timestamp") or datetime.now(timezone.utc).isoformat()
    # Count verification decisions for detail
    decision_counts = {}
    for v in verification_results.values():
        d = v.decision if hasattr(v, "decision") else v.get("decision")
        decision_counts[d] = decision_counts.get(d, 0) + 1
    pre_timeline = [
        create_timeline_event("discovery_complete", detail={"candidate_count": manifest.get("candidate_count", 0)}, actor="discovery", ts=ts_base),
        create_timeline_event("normalization_complete", detail={"candidate_count": manifest.get("candidate_count", 0)}, actor="normalizer", ts=ts_base),
        create_timeline_event("acquisition_complete", detail={
            "candidate_count": manifest.get("candidate_count", 0),
            "acquired_count": manifest.get("acquired_count", 0),
            "failed_count": manifest.get("failed_count", 0),
        }, actor="acquisition", ts=ts_base),
        create_timeline_event("verification_complete", detail={
            "verified_count": len(verification_results),
            "decisions": decision_counts,
        }, actor="verification", ts=ts_base),
    ]

    # 4. Evidence builder (adds evidence_built and computes root hash including verification results)
    envelope = build_evidence(
        enriched_manifest,
        query_image=image_path,
        timeline=pre_timeline,
        output_dir=evidence_output_dir,
        write_files=True,
    )

    # 5. Runtime EventBus (all events, hashed + runtime)
    event_bus = EventBus()
    for ev in pre_timeline:
        event_bus.emit(ev)
    # evidence_built from envelope (last event after builder recompute)
    for ev in envelope.timeline:
        if ev.event == "evidence_built":
            event_bus.emit(ev)
            break

    anchor = None
    anchor_is_inmemory = None
    if register_on_chain:
        client = blockchain_client or _get_default_client()
        anchor_is_inmemory = _is_inmemory_client(client)
        anchor = register_evidence(envelope, client, anchor_dir=anchor_dir, write_anchor=True)
        # Tag anchor with mode for UI distinction
        anchor["_inmemory"] = anchor_is_inmemory
        anchor["_mode"] = "IN-MEMORY ANCHOR" if anchor_is_inmemory else "ANCHORED ON BLOCKCHAIN"
        logger.info("AUDIT ANCHOR MODE: %s contract=%s tx=%s", anchor["_mode"], anchor.get("contract_address"), anchor.get("transaction_hash"))
        # blockchain_registered stays OUTSIDE envelope, only in bus
        event_bus.emit_event(
            "blockchain_registered",
            detail={
                "evidence_hash": envelope.evidence_hash,
                "transaction_hash": anchor.get("transaction_hash"),
                "block_number": anchor.get("block_number"),
                "contract_address": anchor.get("contract_address"),
                "mode": anchor["_mode"],
            },
            actor="blockchain",
        )
    else:
        logger.info("AUDIT ANCHOR MODE: NOT REGISTERED")

    logger.info("AUDIT RETURNED TO UI: %s candidates in envelope", len(envelope.candidates))

    return {
        "manifest": manifest,
        "verification_results": verification_results,
        "enriched_manifest": enriched_manifest,
        "envelope": envelope,
        "anchor": anchor,
        "event_bus": event_bus,
        "anchor_is_inmemory": anchor_is_inmemory,
    }


def verify_pipeline(
    evidence_path: str | Path,
    blockchain_client: Optional[BlockchainClient] = None,
    anchor_dir: str | Path = "data/blockchain",
):
    """Verify evidence artifact (offline + optional on-chain)."""
    return verify_offline(envelope_path=evidence_path, client=blockchain_client, anchor_dir=anchor_dir)
