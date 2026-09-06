"""Tests for the runtime image search POC."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search.searcher import search_image, _validate_image
from search.providers.primary import MicrosoftFoundryProvider
from search.providers.backup import DockerHubProvider


class TestValidateImage(unittest.TestCase):
    def test_valid_image(self):
        path = Path("data/input/query.jpg")
        result = _validate_image(str(path))
        self.assertEqual(result.name, "query.jpg")

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            _validate_image("data/input/nonexistent.jpg")

    def test_invalid_path(self):
        with self.assertRaises(ValueError):
            _validate_image("")

    def test_non_image_file(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode='w')
        tmp.write("not an image")
        tmp.close()
        try:
            with self.assertRaises(ValueError):
                _validate_image(tmp.name)
        finally:
            os.unlink(tmp.name)


class TestMicrosoftFoundryProvider(unittest.TestCase):
    def setUp(self):
        self.provider = MicrosoftFoundryProvider()

    def test_search_returns_results(self):
        results = self.provider.search(query="pytorch", n=5)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_search_result_structure(self):
        results = self.provider.search(query="azureml", n=3)
        for r in results:
            self.assertIn("source_url", r)
            self.assertIn("image_url", r)
            self.assertIn("title", r)
            self.assertIn("search_rank", r)
            self.assertIn("provider", r)

    def test_search_empty_query(self):
        results = self.provider.search(query="x", n=10)
        self.assertIsInstance(results, list)


class TestDockerHubProvider(unittest.TestCase):
    def setUp(self):
        self.provider = DockerHubProvider()

    def test_search_returns_results(self):
        results = self.provider.search(query="pytorch", n=5)
        self.assertIsInstance(results, list)

    def test_search_result_structure(self):
        results = self.provider.search(query="nginx", n=3)
        for r in results:
            self.assertIn("source_url", r)
            self.assertIn("image_url", r)
            self.assertIn("title", r)
            self.assertIn("search_rank", r)
            self.assertIn("provider", r)

    def test_search_with_empty_results(self):
        results = self.provider.search(query="unlikely_repo_xyz", n=2)
        self.assertIsInstance(results, list)


class TestSearcher(unittest.TestCase):
    def test_search_image_valid(self):
        results = search_image("data/input/query.jpg")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_search_image_missing(self):
        with self.assertRaises(FileNotFoundError):
            search_image("data/input/nonexistent.jpg")

    def test_search_image_non_image(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode='w')
        tmp.write("not an image")
        tmp.close()
        try:
            with self.assertRaises(ValueError):
                search_image(tmp.name)
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
