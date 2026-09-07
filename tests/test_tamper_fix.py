"""Focused tests for tamper demo 200→404 fix."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.builder import build_evidence
from app import app

class TestTamperDemoFix(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        app.config['TESTING'] = True
        self.client = app.test_client()
        # create controlled evidence file with 2 candidates
        manifest = {
            "query_image": "query.jpg",
            "candidate_count": 2,
            "acquired_count": 2,
            "failed_count": 0,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "candidates": [
                {"candidate_id":"cand_001","status":"success","provider":"visual-search-acquisition","local_path":None,"content_type":"image/jpeg","file_size":100,"content_sha256":"a"*64,"source_url":"https://example.com/p1","image_url":"https://example.com/img1.jpg","thumbnail_url":None,"title":None,"search_rank":1,"discovery_provider":"yandex-visual-search"},
                {"candidate_id":"cand_002","status":"success","provider":"visual-search-acquisition","local_path":None,"content_type":"image/jpeg","file_size":100,"content_sha256":"b"*64,"source_url":"https://example.com/p2","image_url":"https://example.com/img2.jpg","thumbnail_url":None,"title":None,"search_rank":2,"discovery_provider":"yandex-visual-search"},
            ]
        }
        self.ev = build_evidence(manifest, query_image="query.jpg", pipeline_run_id="tamper-fix-test-001", created_at="2026-09-07T00:00:00+00:00", output_dir="data/evidence", write_files=True)
        self.orig_path = f"data/evidence/evidence_tamper-fix-test-001.json"
        self.assertTrue(Path(self.orig_path).exists())

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_repeated_tamper_from_original_always_200(self):
        """Each tamper operation starting from original must return 200 and valid=false."""
        for field in ["score", "score", "decision", "order", "timeline"]:
            resp = self.client.post('/api/tamper_demo', json={"path": self.orig_path, "field": field})
            self.assertEqual(resp.status_code, 200, f"field {field} should be 200, got {resp.status_code}")
            j = resp.get_json()
            self.assertIn("result", j)
            self.assertFalse(j["result"]["valid"], f"field {field} tampered should be invalid")

    def test_original_still_valid_after_tampers(self):
        """Original evidence still reports valid=true after multiple tampers."""
        for field in ["score","decision","order","timeline"]:
            self.client.post('/api/tamper_demo', json={"path": self.orig_path, "field": field})
        # verify original
        resp = self.client.post('/api/verify', json={"path": self.orig_path})
        j = resp.get_json()
        self.assertTrue(j["valid"], "original should remain valid")

    def test_tampered_source_rejected(self):
        """Tampered file must not be usable as source for next tamper (400, not 404 loop)."""
        first = self.client.post('/api/tamper_demo', json={"path": self.orig_path, "field": "score"})
        self.assertEqual(first.status_code, 200)
        tampered = first.get_json()["tampered_path"]
        # try to tamper the tampered file
        second = self.client.post('/api/tamper_demo', json={"path": tampered, "field": "score"})
        self.assertEqual(second.status_code, 400)
        self.assertIn("original", second.get_json()["error"].lower())

    def test_tampered_files_do_not_overwrite_original(self):
        """Original file content must not be modified by tamper."""
        before = json.loads(Path(self.orig_path).read_text())
        before_hash = before["evidence_hash"]
        self.client.post('/api/tamper_demo', json={"path": self.orig_path, "field": "score"})
        after = json.loads(Path(self.orig_path).read_text())
        self.assertEqual(after["evidence_hash"], before_hash)
        self.assertEqual(after, before)

    def test_all_tamper_fields_produce_invalid(self):
        """Score, decision, order, timeline each produce valid=false."""
        for field in ["score","decision","order","timeline"]:
            resp = self.client.post('/api/tamper_demo', json={"path": self.orig_path, "field": field})
            self.assertEqual(resp.status_code, 200)
            res = resp.get_json()["result"]
            self.assertFalse(res["valid"])
            # Ensure mismatches reported
            self.assertTrue(len(res.get("mismatches", [])) > 0)

    def test_missing_path_returns_404_safe(self):
        """If backend cannot find original, return safe error without exposing paths."""
        resp = self.client.post('/api/tamper_demo', json={"path": "data/evidence/nonexistent_12345.json", "field": "score"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.get_json()["error"].lower())
        # Ensure no absolute path leaked
        self.assertNotIn("/tmp", resp.get_json()["error"])
        self.assertNotIn("/Users", resp.get_json()["error"])

if __name__ == "__main__":
    unittest.main()
