import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from search.acquisition.base import AcquisitionManager
from search.acquisition.mcr import MCRAcquisitionProvider
from search.acquisition.dockerhub import DockerHubAcquisitionProvider
from search.acquisition.visual import VisualSearchAcquisitionProvider

logger = logging.getLogger(__name__)


def run_acquisition_pipeline(candidates: list) -> dict:
    visual_provider = VisualSearchAcquisitionProvider()
    mcr_provider = MCRAcquisitionProvider()
    docker_provider = DockerHubAcquisitionProvider()
    manager = AcquisitionManager(primary_provider=visual_provider, backup_provider=None)

    results = manager.acquire_batch(candidates)

    success_count = sum(1 for r in results if r["status"] == "success")
    fail_count = sum(1 for r in results if r["status"] == "failed")

    manifest = {
        "query_image": None,
        "candidate_count": len(candidates),
        "acquisition_attempted": len(candidates),
        "acquired_count": success_count,
        "failed_count": fail_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidates": results,
    }

    manifest_path = Path("data/debug/candidate_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n[ACQUISITION] Attempted: {len(candidates)}")
    print(f"[ACQUISITION] Successfully acquired: {success_count}")
    print(f"[ACQUISITION] Failed: {fail_count}")
    print(f"[MANIFEST] Saved: data/debug/candidate_manifest.json")

    return manifest


def run_pipeline(image_path="data/input/query.jpg"):
    from search.searcher import search_image, run_search_and_save
    from search.normalizer import normalize_results
    from search.retriever import print_pipeline_summary

    search_results = search_image(image_path)
    print(f"\n[SEARCH] Candidates discovered: {len(search_results)}")

    normalized = normalize_results(search_results)
    print(f"[NORMALIZATION] Candidates normalized: {len(normalized)}")

    manifest = run_acquisition_pipeline(normalized)
    print_pipeline_summary(manifest)

    return manifest


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    run_pipeline()
