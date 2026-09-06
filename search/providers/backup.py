import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class DockerHubProvider:
    def __init__(self):
        self.name = "dockerhub"
        self.registry = "docker.io"
        self.base_url = "https://hub.docker.com/v2/repositories"

    def search(self, query: str, n: int = 20) -> List[dict]:
        logger.info("Searching Docker Hub for query: %s", query)
        results = []

        # Try common repository patterns
        repo_names = [
            query,
            f"library/{query}",
            f"{query}/{query}",
        ]

        for repo_name in repo_names:
            if len(results) >= n:
                break
            try:
                url = f"{self.base_url}/{repo_name}/tags/"
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    continue
                data = response.json()
                tag_results = data.get("results", [])
                for i, tag_data in enumerate(tag_results[: n - len(results)]):
                    results.append({
                        "source_url": f"https://hub.docker.com/_/{repo_name}",
                        "image_url": f"docker.io/{repo_name}:{tag_data.get('name', 'latest')}",
                        "thumbnail_url": None,
                        "title": f"{repo_name}:{tag_data.get('name', 'latest')}",
                        "search_rank": len(results) + i + 1,
                        "provider": self.name,
                    })
            except requests.RequestException as e:
                logger.warning("Failed to query repo '%s': %s", repo_name, e)
                continue

        logger.info("DockerHub returned %d results for query '%s'", len(results), query)
        return results

    def get_image(self, name: str, tag: str = "latest") -> Optional[dict]:
        try:
            url = f"{self.base_url}/{name}/tags/?n=1"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return {"name": name, "tag": tag, "registry": self.registry}
        except requests.RequestException:
            return None
