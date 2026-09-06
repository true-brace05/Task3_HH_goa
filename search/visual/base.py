from abc import ABC, abstractmethod
from typing import List, Optional


class VisualSearchProvider(ABC):
    def __init__(self):
        self.name = "visual-search-base"

    @abstractmethod
    def search_by_image(self, image_path: str) -> List[dict]:
        pass

    @abstractmethod
    def can_search(self, image_path: str) -> bool:
        pass
