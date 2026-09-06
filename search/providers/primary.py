import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class MicrosoftFoundryProvider:
    def __init__(self):
        self.name = "microsoft-foundry"
        self.registry = "mcr.microsoft.com"
        self.catalog_url = "https://mcr.microsoft.com/v2/_catalog"

    def search(self, query: str, n: int = 20) -> List[dict]:
        logger.info("Searching MCR for query: %s", query)
        try:
            response = requests.get(
                self.catalog_url,
                params={"n": n},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            repos = data.get("repositories", [])
        except requests.RequestException as e:
            logger.error("MCR catalog request failed: %s", e)
            raise RuntimeError(f"MCR provider failed: {e}")

        results = []
        for i, repo_name in enumerate(repos[:n]):
            results.append({
                "source_url": f"https://mcr.microsoft.com/{repo_name}",
                "image_url": f"https://mcr.microsoft.com/{repo_name}",
                "thumbnail_url": None,
                "title": repo_name,
                "search_rank": i + 1,
                "provider": self.name,
            })

        logger.info("MCR returned %d results for query '%s'", len(results), query)
        return results

    def get_image(self, name: str, tag: str = "latest") -> Optional[dict]:
        try:
            url = f"https://mcr.microsoft.com/v2/{name}/tags?n=1"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return {"name": name, "tag": tag, "registry": self.registry}
        except requests.RequestException:
            return None
