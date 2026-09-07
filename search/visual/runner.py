import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from search.searcher import search_image
from search.normalizer import normalize_results
from search.acquisition.runner import run_acquisition_pipeline
from search.retriever import print_pipeline_summary

logger = logging.getLogger(__name__)


def run_pipeline(image_path="data/input/query.jpg"):
    search_results = search_image(image_path)
    print(f"\n[SEARCH] Candidates discovered: {len(search_results)}")

    normalized = normalize_results(search_results)
    print(f"[NORMALIZATION] Candidates normalized: {len(normalized)}")

    manifest = run_acquisition_pipeline(normalized)
    print_pipeline_summary(manifest)

    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_pipeline()
