import logging
import time
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

from search.visual.base import VisualSearchProvider

logger = logging.getLogger(__name__)


class GoogleLensProvider(VisualSearchProvider):
    def __init__(self):
        self.name = "google-lens"
        self.upload_url = "https://www.google.com/searchbyimage/upload"
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
        files = {"encoded_image": (Path(image_path).name, image_bytes, "image/jpeg")}
        data = {"sbisrc": "cr_1_5_2", "hl": "en"}

        try:
            response = requests.post(
                self.upload_url,
                files=files,
                data=data,
                headers=self.headers,
                timeout=20,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to upload image to Google: %s", e)
            return []

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            logger.error("Unexpected response type: %s", content_type)
            return []

        html = response.text

        if "input file" in html.lower() or "upload your image" in html.lower():
            logger.error("Google blocked the request — CAPTCHA or upload form shown")
            return []

        results = self._parse_results(html)
        return results

    def _parse_results(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for img_tile in soup.find_all("a", href=True):
            href = img_tile.get("href", "")
            if not href.startswith("/url?") and not href.startswith("https://www.google.com/url"):
                continue

            title_tag = img_tile.find("h3") or img_tile.find("h4")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            if not title:
                continue

            parsed_url = self._extract_url(href)
            if not parsed_url:
                continue

            thumb = img_tile.find("img")
            thumbnail = thumb.get("src") if thumb else None

            results.append({
                "source_url": parsed_url,
                "image_url": parsed_url,
                "thumbnail_url": thumbnail,
                "title": title,
                "provider": self.name,
            })

        seen = set()
        unique_results = []
        for r in results:
            url = r.get("image_url", "")
            if url not in seen:
                seen.add(url)
                unique_results.append(r)

        return unique_results[:20]

    def _extract_url(self, href: str) -> Optional[str]:
        if href.startswith("/url?"):
            import re
            match = re.search(r"url\?q=([^&]+)", href)
            if match:
                return match.group(1)
            return None
        return href
