import json
import logging
import re
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from PIL import Image

from search.visual.base import VisualSearchProvider

logger = logging.getLogger(__name__)


class YandexVisualSearchProvider(VisualSearchProvider):
    def __init__(self):
        self.name = "yandex-visual-search"
        self.upload_url = "https://yandex.com/images/search"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        self.retry_count = 3
        self.retry_delay = 2

    def can_search(self, image_path: str) -> bool:
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            return False
        valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}
        if path.suffix.lower() not in valid_extensions:
            return False
        try:
            with Image.open(path) as img:
                img.verify()
            return True
        except Exception:
            return False

    def search_by_image(self, image_path: str) -> List[dict]:
        logger.info("[VISUAL SEARCH START] Input: %s", image_path)

        if not self.can_search(image_path):
            logger.error("[VISUAL SEARCH FAILED] Invalid image: %s", image_path)
            raise ValueError(f"Cannot search with invalid image: {image_path}")

        path = Path(image_path)
        results = []

        for attempt in range(self.retry_count):
            try:
                results = self._fetch_results(str(path))
                if results and len(results) > 0:
                    logger.info("[VISUAL SEARCH COMPLETE] Candidates returned: %d", len(results))
                    return results
                logger.warning("Attempt %d/%d returned no results, retrying...", attempt + 1, self.retry_count)
                time.sleep(self.retry_delay)
            except Exception as e:
                logger.warning("Attempt %d/%d failed: %s", attempt + 1, self.retry_count, e)
                time.sleep(self.retry_delay)

        if not results:
            logger.error("[VISUAL SEARCH BLOCKED] Could not retrieve results after %d attempts", self.retry_count)
            return []

        logger.info("[VISUAL SEARCH COMPLETE] Candidates returned: %d", len(results))
        return results

    def _fetch_results(self, image_path: str) -> List[dict]:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        files = {"upfile": (Path(image_path).name, image_bytes, "image/jpeg")}
        params = {
            "rpt": "imageview",
            "format": "json",
            "request": '{"blocks":[{"block":"b-page_type_search-by-image__link"}]}'
        }

        try:
            response = requests.post(
                self.upload_url,
                params=params,
                files=files,
                headers=self.headers,
                timeout=20,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to upload image to Yandex: %s", e)
            return []

        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            return self._parse_json_response(response.text)
        elif "text/html" in content_type:
            return self._parse_html_response(response.text, response.url)
        else:
            logger.error("Unexpected response type: %s", content_type)
            return []

    def _parse_json_response(self, response_text: str) -> List[dict]:
        try:
            data = json.loads(response_text)
            if "blocks" in data and len(data["blocks"]) > 0:
                params = data["blocks"][0].get("params", {})
                cbir_id = params.get("cbirId", "")
                
                if cbir_id:
                    search_url = f"https://yandex.com/images/search?cbir_id={cbir_id}&rpt=imageview"
                    return self._fetch_search_results(search_url)
            return []
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error("Failed to parse JSON response: %s", e)
            return []

    def _parse_html_response(self, html: str, base_url: str) -> List[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if "cbir_id" not in href:
                continue

            img_url = self._extract_image_url_from_href(href)
            if not img_url:
                continue

            source_url = self._extract_source_url_from_href(href, base_url)

            title_tag = a_tag.find(["h3", "h4", "span"], class_=re.compile("title|snippet"))
            title = title_tag.get_text(strip=True) if title_tag else None

            results.append({
                "source_url": source_url,
                "image_url": img_url,
                "thumbnail_url": None,
                "title": title,
                "provider": self.name,
            })

        seen = set()
        unique_results = []
        for r in results:
            url = r.get("image_url", "")
            if url and url not in seen:
                seen.add(url)
                unique_results.append(r)

        return unique_results[:20]

    def _extract_image_url_from_href(self, href: str) -> Optional[str]:
        try:
            if href.startswith("/"):
                href = "https://yandex.com" + href

            parsed = urlparse(href)
            params = parse_qs(parsed.query)

            if "img_url" in params:
                return unquote(params["img_url"][0])

            if "url" in params:
                url = unquote(params["url"][0])
                if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]):
                    return url

            return None
        except Exception:
            return None

    def _extract_source_url_from_href(self, href: str, base_url: str) -> Optional[str]:
        try:
            if href.startswith("/"):
                href = "https://yandex.com" + href

            parsed = urlparse(href)
            params = parse_qs(parsed.query)

            if "url" in params:
                url = unquote(params["url"][0])
                if not any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]):
                    return url

            return None
        except Exception:
            return None

    def _fetch_search_results(self, search_url: str) -> List[dict]:
        try:
            response = requests.get(
                search_url,
                headers=self.headers,
                timeout=20,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to fetch search results: %s", e)
            return []

        return self._parse_html_response(response.text, search_url)
