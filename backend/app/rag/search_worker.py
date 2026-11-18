
import json
import sys
import time


def log_timing(message: str, seconds: float):
    # stderr pour ne pas perturber le JSON sur stdout.
    print(
        f"[PERF] {message}: {seconds:.2f}s",
        file=sys.stderr,
        flush=True
    )


def main():
    start_total = time.perf_counter()

    question = sys.argv[1]
    limit = int(sys.argv[2])

    start_import = time.perf_counter()

    from app.rag.retriever import search_documents

    log_timing(
        "Importation Python / PyTorch",
        time.perf_counter() - start_import
    )

    start_search = time.perf_counter()

    documents = search_documents(
        question,
        limit=limit
    )

    log_timing(
        "Recherche BGE-M3 + Qdrant",
        time.perf_counter() - start_search
    )

    log_timing(
        "Total worker",
        time.perf_counter() - start_total
    )

    print(
        json.dumps(
            documents,
            ensure_ascii=False
        ),
        flush=True
    )


if __name__ == "__main__":
    main()
