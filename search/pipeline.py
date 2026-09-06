from search.searcher import search_image, run_search_and_save
from search.normalizer import normalize_results
from search.retriever import retrieve_candidates, print_pipeline_summary


def run_pipeline(image_path="data/input/query.jpg"):
    search_results = search_image(image_path)
    normalized = normalize_results(search_results)
    manifest = retrieve_candidates(normalized, output_dir="data/candidates")
    print_pipeline_summary(manifest)
    return manifest


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_pipeline()
