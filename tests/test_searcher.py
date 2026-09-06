"""Tests for the runtime image search POC."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests.exceptions

sys.path.insert(0, str(Path(__file__).parent.parent))

from search.searcher import search_image, _validate_image
from search.providers.primary import MicrosoftFoundryProvider
from search.providers.backup import DockerHubProvider
from search.normalizer import normalize_results
from search.retriever import retrieve_candidates
from search.acquisition.base import AcquisitionManager
from search.acquisition.mcr import MCRAcquisitionProvider
from search.acquisition.dockerhub import DockerHubAcquisitionProvider
from search.visual.google_lens import GoogleLensProvider
from search.visual.yandex import YandexVisualSearchProvider


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


class TestNormalizer(unittest.TestCase):
    def test_normal_result(self):
        raw = [{
            "candidate_id": "cand_000",
            "source_url": "https://example.com/src",
            "image_url": "https://example.com/img.jpg",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "title": "Test Image",
            "search_rank": 1,
            "provider": "microsoft-foundry",
        }]
        normalized = normalize_results(raw)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["candidate_id"], "cand_001")
        self.assertEqual(normalized[0]["title"], "Test Image")
        self.assertEqual(normalized[0]["search_rank"], 1)
        self.assertEqual(normalized[0]["provider"], "microsoft-foundry")

    def test_missing_optional_fields(self):
        raw = [{
            "image_url": "https://example.com/img.jpg",
            "provider": "microsoft-foundry",
            "search_rank": 1,
        }]
        normalized = normalize_results(raw)
        self.assertEqual(len(normalized), 1)
        self.assertIsNone(normalized[0]["title"])
        self.assertIsNone(normalized[0]["thumbnail_url"])
        self.assertIsNone(normalized[0]["source_url"])

    def test_invalid_url(self):
        raw = [{
            "image_url": "not-a-url",
            "provider": "microsoft-foundry",
            "search_rank": 1,
        }]
        normalized = normalize_results(raw)
        self.assertEqual(len(normalized), 0)

    def test_duplicate_handling(self):
        raw = [
            {"image_url": "https://example.com/img.jpg", "provider": "microsoft-foundry", "search_rank": 1},
            {"image_url": "https://example.com/img.jpg", "provider": "microsoft-foundry", "search_rank": 2},
        ]
        normalized = normalize_results(raw)
        self.assertEqual(len(normalized), 1)

    def test_empty_results(self):
        normalized = normalize_results([])
        self.assertEqual(normalized, [])

    def test_malformed_result(self):
        raw = ["not a dict", {"image_url": "https://example.com/img.jpg", "provider": "microsoft-foundry", "search_rank": 1}]
        normalized = normalize_results(raw)
        self.assertEqual(len(normalized), 1)

    def test_rank_preserved(self):
        raw = [
            {"image_url": "https://example.com/a.jpg", "provider": "microsoft-foundry", "search_rank": 5},
            {"image_url": "https://example.com/b.jpg", "provider": "microsoft-foundry", "search_rank": 10},
        ]
        normalized = normalize_results(raw)
        self.assertEqual(normalized[0]["search_rank"], 5)
        self.assertEqual(normalized[1]["search_rank"], 10)

    def test_deterministic_ids(self):
        raw = [
            {"image_url": "https://example.com/a.jpg", "provider": "microsoft-foundry", "search_rank": 1},
            {"image_url": "https://example.com/b.jpg", "provider": "microsoft-foundry", "search_rank": 2},
        ]
        normalized = normalize_results(raw)
        self.assertEqual(normalized[0]["candidate_id"], "cand_001")
        self.assertEqual(normalized[1]["candidate_id"], "cand_002")


class TestRetriever(unittest.TestCase):
    def test_successful_retrieval(self):
        candidate = {
            "candidate_id": "cand_001",
            "image_url": "https://example.com/img.jpg",
            "search_rank": 1,
        }
        with patch("search.retriever.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"fake image data"
            mock_response.headers = {"content-type": "image/jpeg"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            with patch("search.retriever.Image.open") as mock_img:
                mock_img.return_value.verify = MagicMock()
                mock_img.return_value.format = "JPEG"
                result = retrieve_candidates([candidate], output_dir="data/debug/test_candidates")
                self.assertEqual(result["candidate_count"], 1)
                self.assertEqual(result["candidates"][0]["retrieval_status"], "success")

    def test_http_failure(self):
        candidate = {
            "candidate_id": "cand_001",
            "image_url": "https://example.com/forbidden.jpg",
            "search_rank": 1,
        }
        with patch("search.retriever.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(status_code=403))
            mock_get.return_value = mock_response
            result = retrieve_candidates([candidate], output_dir="data/debug/test_candidates2")
            self.assertEqual(result["candidates"][0]["retrieval_status"], "failed")

    def test_missing_image_url(self):
        candidate = {
            "candidate_id": "cand_001",
            "search_rank": 1,
        }
        result = retrieve_candidates([candidate], output_dir="data/debug/test_candidates3")
        self.assertEqual(result["candidates"][0]["retrieval_status"], "failed")
        self.assertEqual(result["candidates"][0]["error"], "missing image URL")

    def test_empty_candidates(self):
        result = retrieve_candidates([], output_dir="data/debug/test_candidates4")
        self.assertEqual(result["candidate_count"], 0)

    def test_multiple_candidates_one_fails(self):
        candidates = [
            {"candidate_id": "cand_001", "image_url": "https://example.com/img1.jpg", "search_rank": 1},
            {"candidate_id": "cand_002", "image_url": "", "search_rank": 2},
        ]
        with patch("search.retriever.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"fake image data"
            mock_response.headers = {"content-type": "image/jpeg"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            with patch("search.retriever.Image.open") as mock_img:
                mock_img.return_value.verify = MagicMock()
                mock_img.return_value.format = "JPEG"
                result = retrieve_candidates(candidates, output_dir="data/debug/test_candidates5")
                self.assertEqual(result["candidate_count"], 2)
                self.assertEqual(result["retrieved_count"] + result["failed_count"], 2)


class TestAcquisitionBase(unittest.TestCase):
    def test_acquisition_manager_creation(self):
        mcr = MCRAcquisitionProvider()
        docker = DockerHubAcquisitionProvider()
        manager = AcquisitionManager(primary_provider=mcr, backup_provider=docker)
        self.assertIsNotNone(manager)

    def test_acquisition_manager_no_backup(self):
        mcr = MCRAcquisitionProvider()
        manager = AcquisitionManager(primary_provider=mcr)
        self.assertIsNotNone(manager)
        self.assertIsNone(manager.backup)

    def test_mcr_can_acquire(self):
        mcr = MCRAcquisitionProvider()
        candidate = {
            "candidate_id": "cand_001",
            "image_url": "https://mcr.microsoft.com/samples/test",
            "provider": "microsoft-foundry",
        }
        self.assertTrue(mcr.can_acquire(candidate))

    def test_mcr_cannot_acquire_non_mcr(self):
        mcr = MCRAcquisitionProvider()
        candidate = {
            "candidate_id": "cand_001",
            "image_url": "https://example.com/img.jpg",
            "provider": "dockerhub",
        }
        self.assertFalse(mcr.can_acquire(candidate))

    def test_dockerhub_can_acquire(self):
        docker = DockerHubAcquisitionProvider()
        candidate = {
            "candidate_id": "cand_001",
            "image_url": "docker.io/test/repo",
            "provider": "dockerhub",
        }
        self.assertTrue(docker.can_acquire(candidate))

    def test_dockerhub_cannot_acquire_missing_url(self):
        docker = DockerHubAcquisitionProvider()
        candidate = {"candidate_id": "cand_001", "search_rank": 1}
        self.assertFalse(docker.can_acquire(candidate))

    def test_acquire_missing_url(self):
        mcr = MCRAcquisitionProvider()
        candidate = {"candidate_id": "cand_001", "search_rank": 1}
        result = mcr.acquire(candidate)
        self.assertEqual(result["status"], "failed")
        self.assertIn("error", result)

    def test_acquire_malformed_candidate(self):
        mcr = MCRAcquisitionProvider()
        candidate = {}
        result = mcr.acquire(candidate)
        self.assertIn(result["status"], ["failed"])

    def test_fallback_primary_failure(self):
        mcr = MCRAcquisitionProvider()
        docker = DockerHubAcquisitionProvider()
        manager = AcquisitionManager(primary_provider=mcr, backup_provider=docker)
        # Both providers will fail for real network calls, but manager should handle it
        candidate = {"candidate_id": "cand_001", "image_url": "https://invalid.invalid/test", "provider": "microsoft-foundry"}
        result = manager.acquire(candidate)
        self.assertIn(result["status"], ["failed"])

    def test_primary_success_backup_not_called(self):
        mcr = MCRAcquisitionProvider()
        docker = DockerHubAcquisitionProvider()
        manager = AcquisitionManager(primary_provider=mcr, backup_provider=docker)
        # Mock the MCR provider to succeed
        with patch.object(mcr, 'acquire') as mock_acquire:
            mock_acquire.return_value = {"candidate_id": "cand_001", "status": "success", "provider": "mcr-acquisition"}
            with patch.object(docker, 'acquire') as mock_docker_acquire:
                candidate = {"candidate_id": "cand_001", "image_url": "https://mcr.microsoft.com/test", "provider": "microsoft-foundry"}
                result = manager.acquire(candidate)
                self.assertEqual(result["status"], "success")
                mock_docker_acquire.assert_not_called()

    def test_provenance_preserved(self):
        mcr = MCRAcquisitionProvider()
        candidate = {
            "candidate_id": "cand_001",
            "provider": "microsoft-foundry",
            "search_rank": 1,
            "source_url": "https://mcr.microsoft.com/samples/test",
            "image_url": "https://mcr.microsoft.com/samples/test",
        }
        result = mcr.acquire(candidate)
        self.assertEqual(result["candidate_id"], "cand_001")


class TestGoogleLensProvider(unittest.TestCase):
    def setUp(self):
        self.provider = GoogleLensProvider()

    def test_provider_name(self):
        self.assertEqual(self.provider.name, "google-lens")

    def test_can_search_valid_image(self):
        result = self.provider.can_search("data/input/query.jpg")
        self.assertTrue(result)

    def test_can_search_invalid_path(self):
        result = self.provider.can_search("data/input/nonexistent.jpg")
        self.assertFalse(result)

    def test_can_search_non_image(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode='w')
        tmp.write("not an image")
        tmp.close()
        try:
            result = self.provider.can_search(tmp.name)
            self.assertFalse(result)
        finally:
            os.unlink(tmp.name)

    def test_search_by_image_returns_list(self):
        results = self.provider.search_by_image("data/input/query.jpg")
        self.assertIsInstance(results, list)

    def test_search_by_image_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.provider.search_by_image("data/input/nonexistent.jpg")

    def test_search_by_image_non_image_raises(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode='w')
        tmp.write("not an image")
        tmp.close()
        try:
            with self.assertRaises(ValueError):
                self.provider.search_by_image(tmp.name)
        finally:
            os.unlink(tmp.name)


class TestYandexVisualSearchProvider(unittest.TestCase):
    def setUp(self):
        self.provider = YandexVisualSearchProvider()

    def test_provider_name(self):
        self.assertEqual(self.provider.name, "yandex-visual-search")

    def test_can_search_valid_image(self):
        result = self.provider.can_search("data/input/query.jpg")
        self.assertTrue(result)

    def test_can_search_invalid_path(self):
        result = self.provider.can_search("data/input/nonexistent.jpg")
        self.assertFalse(result)

    def test_can_search_non_image(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode='w')
        tmp.write("not an image")
        tmp.close()
        try:
            result = self.provider.can_search(tmp.name)
            self.assertFalse(result)
        finally:
            os.unlink(tmp.name)

    def test_search_by_image_returns_list(self):
        results = self.provider.search_by_image("data/input/query.jpg")
        self.assertIsInstance(results, list)

    def test_search_by_image_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.provider.search_by_image("data/input/nonexistent.jpg")

    def test_search_by_image_non_image_raises(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode='w')
        tmp.write("not an image")
        tmp.close()
        try:
            with self.assertRaises(ValueError):
                self.provider.search_by_image(tmp.name)
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
