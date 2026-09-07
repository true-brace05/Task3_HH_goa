"""Focused UI security regression tests for Flask app."""

import io
import unittest
from pathlib import Path

from app import app

class TestUISecurity(unittest.TestCase):
    def test_candidate_image_blocks_passwd(self):
        with app.test_client() as c:
            r = c.get('/candidate_image?path=/etc/passwd')
            self.assertEqual(r.status_code, 403)
            self.assertIn('forbidden', r.json.get('error','').lower())

    def test_candidate_image_blocks_hosts(self):
        with app.test_client() as c:
            r = c.get('/candidate_image?path=/etc/hosts')
            self.assertEqual(r.status_code, 403)

    def test_candidate_image_allows_valid_via_token(self):
        from pathlib import Path as P
        # create a valid allowed image in data/candidates
        p = P("data/candidates") / "test_ui_sec.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (10,10), color="red").save(p)
        try:
            # Register via internal map by calling investigate or directly via helper
            from app import _register_image
            token = _register_image(p)
            with app.test_client() as c:
                r = c.get(f'/image/{token}')
                self.assertEqual(r.status_code, 200)
                # legacy path with allowlist should also be 403 for absolute outside? but token works
        finally:
            if p.exists():
                p.unlink()

    def test_investigate_no_trace_leakage(self):
        with app.test_client() as c:
            r = c.post('/api/investigate', data={}, content_type='multipart/form-data')
            self.assertEqual(r.status_code, 400)
            self.assertNotIn('trace', r.json)

    def test_investigate_corrupt_no_absolute_path(self):
        with app.test_client() as c:
            r = c.post('/api/investigate', data={'image': (io.BytesIO(b'\x00\x01'), 'bad.jpg')}, content_type='multipart/form-data')
            self.assertEqual(r.status_code, 500)
            self.assertNotIn('trace', r.json)
            err = r.json.get('error','')
            self.assertNotIn('/var', err)
            self.assertNotIn('/tmp', err)

    def test_investigate_response_no_absolute_paths(self):
        q = Path("/tmp/real_face_validation/query.jpg")
        if not q.exists():
            self.skipTest("no real face fixture")
        with app.test_client() as c:
            with open(q,'rb') as f:
                r = c.post('/api/investigate', data={'image': (f,'q.jpg')}, content_type='multipart/form-data')
                self.assertEqual(r.status_code, 200)
                j = r.json
                self.assertNotIn('query_image', j)  # absolute removed
                self.assertIn('query_url', j)
                for cand in j.get('candidates',[]):
                    self.assertNotIn('local_path', cand)
                    if cand.get('image_url'):
                        self.assertTrue(cand['image_url'].startswith('/image/'))
                        self.assertNotIn('/var', cand['image_url'])
                        self.assertNotIn('/tmp', cand['image_url'])

    def test_verify_no_trace(self):
        with app.test_client() as c:
            r = c.post('/api/verify', json={"path":"/nonexistent/evidence.json"})
            self.assertEqual(r.status_code, 404)
            self.assertNotIn('trace', r.json)
            self.assertNotIn('/nonexistent', r.json.get('error',''))

    def test_tamper_still_detects(self):
        real = Path("/tmp/real_evidence_test/evidence_real-validation-0001.json")
        if not real.exists():
            self.skipTest("no real evidence")
        with app.test_client() as c:
            r = c.post('/api/tamper_demo', json={"path": str(real), "field":"score"})
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json['result']['valid'])
            # tampered_path should be basename only, no absolute
            self.assertNotIn('/var', r.json['tampered_path'])
            self.assertNotIn('/tmp', r.json['tampered_path'])

if __name__ == "__main__":
    unittest.main()
