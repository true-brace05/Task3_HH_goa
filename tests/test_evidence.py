"""Phase 1 Evidence Foundation tests — deterministic Evidence Foundation.

Covers:
- canonicalization
- SHA-256
- schema validation
- builder (real manifest fixture)
"""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.canonical import canonical_dumps
from evidence.hash import sha256_hex, hash_candidate, hash_envelope
from evidence.schema import CandidateEvidence, EvidenceEnvelope, TimelineEvent, VerificationData
from evidence.builder import build_evidence
from evidence.timeline import TimelineCollector, create_timeline_event


# Real manifest fixture based on docs/discovery_handoff.md + search/acquisition/visual.py
FIXTURE_MANIFEST = {
    "query_image": "query.jpg",
    "candidate_count": 3,
    "acquisition_attempted": 3,
    "acquired_count": 2,
    "failed_count": 1,
    "timestamp": "2026-09-06T12:00:00+00:00",
    "candidates": [
        {
            "candidate_id": "cand_001",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_001.jpeg",
            "content_type": "image/jpeg",
            "file_size": 15956,
            "content_sha256": "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95",
            "source_url": "https://example.com/page1",
            "image_url": "https://example.com/img1.jpg",
            "thumbnail_url": None,
            "title": None,
            "search_rank": 1,
            "discovery_provider": "yandex-visual-search",
        },
        {
            "candidate_id": "cand_002",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_002.png",
            "content_type": "image/png",
            "file_size": 20480,
            "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "source_url": "https://example.com/page2",
            "image_url": "https://example.com/img2.png",
            "thumbnail_url": "https://example.com/thumb2.jpg",
            "title": "Second",
            "search_rank": 2,
            "discovery_provider": "yandex-visual-search",
        },
        {
            "candidate_id": "cand_003",
            "status": "failed",
            "provider": "visual-search-acquisition",
            "local_path": None,
            "content_type": None,
            "file_size": None,
            "content_sha256": None,
            "source_url": "https://example.com/page3",
            "image_url": "https://example.com/img3.jpg",
            "thumbnail_url": None,
            "title": None,
            "search_rank": 3,
            "discovery_provider": "yandex-visual-search",
            "error": "Timeout",
        },
    ],
}


class TestCanonicalization(unittest.TestCase):
    def test_same_dict_different_insertion_order_identical_bytes(self):
        a = {"b": 1, "a": 2, "c": {"z": 3, "y": 4}}
        b = {"c": {"y": 4, "z": 3}, "a": 2, "b": 1}
        self.assertEqual(canonical_dumps(a), canonical_dumps(b))

    def test_whitespace_absent(self):
        obj = {"a": 1, "b": [2, 3]}
        data = canonical_dumps(obj)
        text = data.decode("utf-8")
        # canonical uses separators (",", ":") — no spaces
        self.assertEqual(text, '{"a":1,"b":[2,3]}')
        self.assertNotIn(" ", text)

    def test_utf8_non_ascii(self):
        obj = {"title": "café — 東京"}
        data = canonical_dumps(obj)
        text = data.decode("utf-8")
        self.assertIn("café", text)
        self.assertIn("東京", text)
        # ensure_ascii=False so bytes are utf-8
        self.assertEqual(data, json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

    def test_none_becomes_null(self):
        obj = {"a": None, "b": 1}
        text = canonical_dumps(obj).decode("utf-8")
        self.assertIn('"a":null', text)

    def test_lists_preserve_order(self):
        obj1 = {"list": [1, 2, 3]}
        obj2 = {"list": [3, 2, 1]}
        self.assertNotEqual(canonical_dumps(obj1), canonical_dumps(obj2))

    def test_nested_dicts_deterministic(self):
        inner1 = {"x": 1, "y": 2}
        inner2 = {"y": 2, "x": 1}
        self.assertEqual(canonical_dumps({"a": inner1}), canonical_dumps({"a": inner2}))

    def test_floats_rejected(self):
        with self.assertRaises(ValueError):
            canonical_dumps({"a": 1.5})
        with self.assertRaises(ValueError):
            canonical_dumps({"a": [1, 2.0]})
        with self.assertRaises(ValueError):
            canonical_dumps({"a": {"b": 3.14}})
        # int is fine
        canonical_dumps({"a": 1})

    def test_float_rejected_nested(self):
        with self.assertRaises(ValueError):
            canonical_dumps([1, None, {"x": float("inf")}])

    def test_no_trailing_newline(self):
        data = canonical_dumps({"a": 1})
        self.assertFalse(data.endswith(b"\n"))

    def test_booleans_preserved(self):
        obj = {"a": True, "b": False}
        text = canonical_dumps(obj).decode("utf-8")
        self.assertIn('"a":true', text)
        self.assertIn('"b":false', text)


class TestSHA256(unittest.TestCase):
    def test_known_sha256(self):
        # well-known vector
        self.assertEqual(sha256_hex(b""), hashlib.sha256(b"").hexdigest())
        self.assertEqual(sha256_hex(b"hello"), hashlib.sha256(b"hello").hexdigest())

    def test_same_candidate_same_hash(self):
        cand_dict = {
            "candidate_id": "cand_001",
            "local_path": "data/candidates/cand_001.jpeg",
            "content_sha256": "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95",
            "source_url": "https://example.com/page1",
            "image_url": "https://example.com/img1.jpg",
            "thumbnail_url": None,
            "title": None,
            "discovery_provider": "yandex-visual-search",
            "search_rank": 1,
            "status": "success",
            "file_size": 15956,
            "content_type": "image/jpeg",
            "evidence_hash": None,
            "verification": {"method": "pending", "score": None, "timestamp": None},
        }
        h1 = hash_candidate(cand_dict)
        h2 = hash_candidate(cand_dict)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_candidate_hash_excludes_evidence_hash(self):
        d1 = {
            "candidate_id": "cand_001", "image_url": "https://example.com/a.jpg",
            "discovery_provider": "yandex-visual-search", "search_rank": 1, "status": "success",
            "verification": {"method": "pending", "score": None, "timestamp": None},
            "evidence_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
        d2 = {
            "candidate_id": "cand_001", "image_url": "https://example.com/a.jpg",
            "discovery_provider": "yandex-visual-search", "search_rank": 1, "status": "success",
            "verification": {"method": "pending", "score": None, "timestamp": None},
            "evidence_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        }
        self.assertEqual(hash_candidate(d1), hash_candidate(d2))

    def test_modifying_one_field_changes_candidate_hash(self):
        base = {
            "candidate_id": "cand_001", "image_url": "https://example.com/a.jpg",
            "discovery_provider": "yandex-visual-search", "search_rank": 1, "status": "success",
            "verification": {"method": "pending", "score": None, "timestamp": None},
        }
        h_base = hash_candidate(base)
        modified = dict(base)
        modified["search_rank"] = 2
        self.assertNotEqual(h_base, hash_candidate(modified))

    def test_same_envelope_same_hash(self):
        env = {"envelope_version": "1.0", "query_image": "q.jpg", "created_at": "2026-09-06T00:00:00+00:00",
               "pipeline_run_id": "test", "candidate_count": 0, "acquired_count": 0,
               "candidates": [], "timeline": [], "evidence_hash": None}
        h1 = hash_envelope(env)
        h2 = hash_envelope(env)
        self.assertEqual(h1, h2)

    def test_envelope_hash_excludes_top_level(self):
        env1 = {"envelope_version": "1.0", "query_image": "q.jpg", "created_at": "2026-09-06T00:00:00+00:00",
                "pipeline_run_id": "test", "candidate_count": 1, "acquired_count": 1,
                "candidates": [{"candidate_id": "cand_001", "image_url": "https://example.com/a.jpg", "discovery_provider": "x", "search_rank": 1, "status": "success", "evidence_hash": "abc", "verification": {"method": "pending", "score": None, "timestamp": None}}],
                "timeline": [], "evidence_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        env2 = dict(env1)
        env2["evidence_hash"] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        self.assertEqual(hash_envelope(env1), hash_envelope(env2))

    def test_modifying_candidate_changes_root_hash(self):
        env_base = {"envelope_version": "1.0", "query_image": "q.jpg", "created_at": "2026-09-06T00:00:00+00:00",
                    "pipeline_run_id": "test", "candidate_count": 1, "acquired_count": 1,
                    "candidates": [{"candidate_id": "cand_001", "image_url": "https://example.com/a.jpg", "discovery_provider": "x", "search_rank": 1, "status": "success", "evidence_hash": "abc", "verification": {"method": "pending", "score": None, "timestamp": None}}],
                    "timeline": [], "evidence_hash": None}
        h_base = hash_envelope(env_base)
        env_mod = {"envelope_version": "1.0", "query_image": "q.jpg", "created_at": "2026-09-06T00:00:00+00:00",
                   "pipeline_run_id": "test", "candidate_count": 1, "acquired_count": 1,
                   "candidates": [{"candidate_id": "cand_001", "image_url": "https://example.com/b.jpg", "discovery_provider": "x", "search_rank": 1, "status": "success", "evidence_hash": "abc", "verification": {"method": "pending", "score": None, "timestamp": None}}],
                   "timeline": [], "evidence_hash": None}
        self.assertNotEqual(h_base, hash_envelope(env_mod))

    def test_modifying_timeline_changes_root_hash(self):
        env_base = {"envelope_version": "1.0", "query_image": "q.jpg", "created_at": "2026-09-06T00:00:00+00:00",
                    "pipeline_run_id": "test", "candidate_count": 0, "acquired_count": 0,
                    "candidates": [], "timeline": [{"ts": "2026-09-06T00:00:00+00:00", "event": "discovery_complete", "detail": {}, "actor": "system"}], "evidence_hash": None}
        env_mod = {"envelope_version": "1.0", "query_image": "q.jpg", "created_at": "2026-09-06T00:00:00+00:00",
                   "pipeline_run_id": "test", "candidate_count": 0, "acquired_count": 0,
                   "candidates": [], "timeline": [{"ts": "2026-09-06T00:00:00+00:00", "event": "acquisition_complete", "detail": {}, "actor": "system"}], "evidence_hash": None}
        self.assertNotEqual(hash_envelope(env_base), hash_envelope(env_mod))


class TestSchemaValidation(unittest.TestCase):
    def test_invalid_image_url_rejected(self):
        with self.assertRaises(ValueError):
            CandidateEvidence(candidate_id="cand_001", image_url="not-a-url", discovery_provider="x", search_rank=1, status="success")
        with self.assertRaises(ValueError):
            CandidateEvidence(candidate_id="cand_001", image_url="ftp://example.com/a.jpg", discovery_provider="x", search_rank=1, status="success")

    def test_invalid_content_sha256_rejected(self):
        with self.assertRaises(ValueError):
            CandidateEvidence(candidate_id="cand_001", image_url="https://example.com/a.jpg", discovery_provider="x", search_rank=1, status="success", content_sha256="short")
        with self.assertRaises(ValueError):
            CandidateEvidence(candidate_id="cand_001", image_url="https://example.com/a.jpg", discovery_provider="x", search_rank=1, status="success", content_sha256="zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")

    def test_valid_sha256_accepted(self):
        c = CandidateEvidence(candidate_id="cand_001", image_url="https://example.com/a.jpg", discovery_provider="x", search_rank=1, status="success", content_sha256="8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95")
        self.assertEqual(c.content_sha256, "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95")

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            CandidateEvidence(candidate_id="cand_001", image_url="https://example.com/a.jpg", discovery_provider="x", search_rank=1, status="invalid")

    def test_valid_failed_candidate_accepted(self):
        c = CandidateEvidence(candidate_id="cand_003", image_url="https://example.com/a.jpg", discovery_provider="x", search_rank=3, status="failed")
        self.assertEqual(c.status, "failed")
        self.assertIsNone(c.content_sha256)
        self.assertIsNone(c.evidence_hash)

    def test_invalid_event_rejected(self):
        with self.assertRaises(ValueError):
            TimelineEvent(ts="2026-09-06T00:00:00+00:00", event="invalid_event")

    def test_valid_events_accepted(self):
        for ev in ["discovery_complete", "normalization_complete", "acquisition_complete", "evidence_built", "blockchain_registered", "verification_complete"]:
            t = TimelineEvent(ts="2026-09-06T00:00:00+00:00", event=ev)
            self.assertEqual(t.event, ev)


class TestBuilder(unittest.TestCase):
    def test_successful_candidates_receive_hashes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="11111111-1111-1111-1111-111111111111", output_dir=tmpdir, write_files=False)
            success = [c for c in env.candidates if c.status == "success"]
            self.assertEqual(len(success), 2)
            for c in success:
                self.assertIsNotNone(c.evidence_hash)
                self.assertEqual(len(c.evidence_hash), 64)

    def test_failed_candidates_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="22222222-2222-2222-2222-222222222222", output_dir=tmpdir, write_files=False)
            failed = [c for c in env.candidates if c.status == "failed"]
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0].candidate_id, "cand_003")
            self.assertIsNone(failed[0].evidence_hash)

    def test_deterministic_ordering(self):
        # Create manifest with out-of-order search_rank
        manifest = {
            "query_image": "q.jpg",
            "timestamp": "2026-09-06T00:00:00+00:00",
            "candidate_count": 2,
            "acquired_count": 2,
            "candidates": [
                {"candidate_id": "cand_002", "image_url": "https://example.com/b.jpg", "discovery_provider": "yandex-visual-search", "search_rank": 2, "status": "success", "content_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
                {"candidate_id": "cand_001", "image_url": "https://example.com/a.jpg", "discovery_provider": "yandex-visual-search", "search_rank": 1, "status": "success", "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="33333333-3333-3333-3333-333333333333", output_dir=tmpdir, write_files=False)
            self.assertEqual(env.candidates[0].candidate_id, "cand_001")
            self.assertEqual(env.candidates[1].candidate_id, "cand_002")

    def test_tie_breaker_candidate_id(self):
        manifest = {
            "query_image": "q.jpg",
            "timestamp": "2026-09-06T00:00:00+00:00",
            "candidate_count": 2,
            "acquired_count": 2,
            "candidates": [
                {"candidate_id": "cand_010", "image_url": "https://example.com/b.jpg", "discovery_provider": "x", "search_rank": 1, "status": "success"},
                {"candidate_id": "cand_002", "image_url": "https://example.com/a.jpg", "discovery_provider": "x", "search_rank": 1, "status": "success"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(manifest, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="44444444-4444-4444-4444-444444444444", output_dir=tmpdir, write_files=False)
            self.assertEqual(env.candidates[0].candidate_id, "cand_002")
            self.assertEqual(env.candidates[1].candidate_id, "cand_010")

    def test_root_hash_generated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="55555555-5555-5555-5555-555555555555", output_dir=tmpdir, write_files=False)
            self.assertIsNotNone(env.evidence_hash)
            self.assertEqual(len(env.evidence_hash), 64)

    def test_evidence_files_written_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_id = "66666666-6666-6666-6666-666666666666"
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id=run_id, output_dir=tmpdir, write_files=True)
            pretty = Path(tmpdir) / f"evidence_{run_id}.json"
            canonical = Path(tmpdir) / f"evidence_{run_id}.canonical.json"
            self.assertTrue(pretty.exists())
            self.assertTrue(canonical.exists())

            # pretty is human-readable JSON with evidence_hash
            with open(pretty) as f:
                pretty_data = json.load(f)
            self.assertEqual(pretty_data["evidence_hash"], env.evidence_hash)

            # canonical file is exact canonical bytes used for root hashing (no evidence_hash)
            with open(canonical, "rb") as f:
                canonical_bytes = f.read()
            # recompute: canonical of envelope without evidence_hash
            env_dict_no_hash = {k: v for k, v in env.to_dict().items() if k != "evidence_hash"}
            expected = canonical_dumps(env_dict_no_hash)
            self.assertEqual(canonical_bytes, expected)
            # verify hash matches
            self.assertEqual(sha256_hex(canonical_bytes), env.evidence_hash)
            # canonical file decoded as utf-8
            canonical_text = canonical_bytes.decode("utf-8")
            self.assertIsInstance(canonical_text, str)
            # no trailing newline in canonical bytes
            self.assertFalse(canonical_bytes.endswith(b"\n"))

    def test_manifest_path_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(FIXTURE_MANIFEST, f)
            out_dir = Path(tmpdir) / "out"
            env = build_evidence(str(manifest_path), created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="77777777-7777-7777-7777-777777777777", output_dir=str(out_dir), write_files=False)
            self.assertEqual(len(env.candidates), 3)

    def test_deterministic_rebuild_except_metadata(self):
        # Same manifest and same injected timestamps/run_id must produce identical hashes
        with tempfile.TemporaryDirectory() as tmpdir:
            env1 = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="88888888-8888-8888-8888-888888888888", output_dir=tmpdir, write_files=False)
            env2 = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="88888888-8888-8888-8888-888888888888", output_dir=tmpdir, write_files=False)
            self.assertEqual(env1.evidence_hash, env2.evidence_hash)
            # candidate hashes deterministic
            for c1, c2 in zip(env1.candidates, env2.candidates):
                self.assertEqual(c1.evidence_hash, c2.evidence_hash)
            # Different run_id should change root (since envelope includes it)
            env3 = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="99999999-9999-9999-9999-999999999999", output_dir=tmpdir, write_files=False)
            self.assertNotEqual(env1.evidence_hash, env3.evidence_hash)

    def test_timeline_integration(self):
        timeline = [
            create_timeline_event("discovery_complete", detail={"candidate_count": 3}, ts="2026-09-06T11:00:00+00:00"),
            create_timeline_event("acquisition_complete", detail={"acquired_count": 2}, ts="2026-09-06T12:00:00+00:00"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, timeline=timeline, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaa1", output_dir=tmpdir, write_files=False)
            # should preserve provided timeline + append evidence_built
            events = [t.event for t in env.timeline]
            self.assertIn("discovery_complete", events)
            self.assertIn("acquisition_complete", events)
            self.assertIn("evidence_built", events)

    def test_no_search_import(self):
        # builder must not import search
        import evidence.builder as mod
        source = Path(mod.__file__).read_text()
        self.assertNotIn("import search", source)
        self.assertNotIn("from search", source)

    def test_content_sha256_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="bbbbbbb1-bbbb-bbbb-bbbb-bbbbbbbbbbb1", output_dir=tmpdir, write_files=False)
            c1 = [c for c in env.candidates if c.candidate_id == "cand_001"][0]
            self.assertEqual(c1.content_sha256, "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95")


class TestTimelineCollector(unittest.TestCase):
    def test_emit_and_get(self):
        col = TimelineCollector()
        ev = create_timeline_event("discovery_complete", detail={"n": 1})
        col.emit(ev)
        self.assertEqual(len(col.get_timeline()), 1)
        self.assertEqual(col.get_timeline()[0].event, "discovery_complete")

    def test_emit_dict(self):
        col = TimelineCollector()
        col.emit({"ts": "2026-09-06T00:00:00+00:00", "event": "acquisition_complete", "detail": {}, "actor": "system"})
        self.assertEqual(col.get_timeline()[0].event, "acquisition_complete")


if __name__ == "__main__":
    unittest.main()
