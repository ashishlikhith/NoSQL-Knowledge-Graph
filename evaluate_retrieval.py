import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

TOP_K = 5
DEFAULT_LABELS = Path(__file__).parent / "evaluation" / "relevance_labels.csv"
DEFAULT_RESULTS = Path(__file__).parent / "evaluation" / "results.csv"
DEFAULT_SUMMARY = Path(__file__).parent / "evaluation" / "summary.txt"
RESULT_FIELDS = [
    "method",
    "query",
    "relevant_document_count",
    "precision_at_5_percent",
    "recall_at_5_percent",
    "mrr_percent",
    "ndcg_at_5_percent",
    "query_latency_ms",
]


def load_labels(path):
    labeled_queries = []
    unlabeled_count = 0

    with path.open(encoding="utf-8-sig", newline="") as label_file:
        reader = csv.DictReader(label_file)
        if not reader.fieldnames or not {"query", "relevant_doc_ids"}.issubset(reader.fieldnames):
            raise ValueError("Labels CSV must have 'query' and 'relevant_doc_ids' columns.")

        for line_number, row in enumerate(reader, start=2):
            query = (row.get("query") or "").strip()
            if not query:
                raise ValueError(f"Missing query on labels CSV line {line_number}.")

            relevant_ids = list(dict.fromkeys(
                doc_id.strip()
                for doc_id in (row.get("relevant_doc_ids") or "").split(";")
                if doc_id.strip()
            ))
            if not relevant_ids:
                unlabeled_count += 1
                continue
            labeled_queries.append((query, relevant_ids))

    return labeled_queries, unlabeled_count


def score_ranking(ranked_ids, relevant_ids, k=TOP_K):
    relevant = set(relevant_ids)
    top_ids = ranked_ids[:k]
    hits = [1 if doc_id in relevant else 0 for doc_id in top_ids]

    precision = sum(hits) / k
    recall = sum(hits) / len(relevant)
    reciprocal_rank = next(
        (1 / rank for rank, doc_id in enumerate(ranked_ids, start=1) if doc_id in relevant),
        0.0,
    )
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, start=1))
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0

    return {
        "precision_at_5_percent": precision * 100,
        "recall_at_5_percent": recall * 100,
        "mrr_percent": reciprocal_rank * 100,
        "ndcg_at_5_percent": ndcg * 100,
    }


def write_results(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as results_file:
        writer = csv.DictWriter(results_file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def run_evaluation(labels_path, results_path, summary_path):
    labeled_queries, unlabeled_count = load_labels(labels_path)
    if not labeled_queries:
        write_results(results_path, [])
        write_summary(
            summary_path,
            "Evaluation not run: no relevance labels are present.\n"
            f"Unlabeled query rows: {unlabeled_count}.\n"
            "Add manually judged, exhaustive relevant document IDs to the labels CSV, "
            "then rerun this script. For a labeled run, MongoDB must be available and "
            "the configured database must contain indexed documents with stored embeddings.",
        )
        print(f"No labeled queries in {labels_path}; no scores were calculated.")
        print(f"Created empty results CSV: {results_path}")
        print(f"Created limitation summary: {summary_path}")
        return 0

    try:
        from pymongo import MongoClient
    except ImportError as error:
        raise RuntimeError(
            f"Missing evaluation dependency: {error.name}. Install project dependencies "
            "with 'python -m pip install -r requirements.txt'."
        ) from error

    database_name = os.getenv("MONGODB_DATABASE", "nosql_enterprise_graph_rag")
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    rows = []

    try:
        with MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) as client:
            client.admin.command("ping")
            chunks = list(client[database_name]["knowledge_chunks"].find(
                {},
                {"_id": 0, "chunk_id": 1, "vector_embedding": 1},
            ))
    except Exception as error:
        raise RuntimeError(
            f"Could not read MongoDB database '{database_name}' using the configured "
            "MONGODB_URI. "
            "Start MongoDB and check MONGODB_URI/MONGODB_DATABASE before running "
            f"a labeled evaluation. Details: {error}"
        ) from error

    if not chunks:
        raise RuntimeError(
            f"MongoDB database '{database_name}' has no documents in "
            "knowledge_chunks. Ingest documents before evaluation."
        )

    missing_vectors = [
        chunk.get("chunk_id", "<missing chunk_id>")
        for chunk in chunks
        if not chunk.get("chunk_id") or not chunk.get("vector_embedding")
    ]
    if missing_vectors:
        raise RuntimeError(
            f"{len(missing_vectors)} stored document(s) lack a chunk_id or vector_embedding; "
            f"examples: {', '.join(missing_vectors[:5])}."
        )

    document_ids = [chunk["chunk_id"] for chunk in chunks]
    document_id_set = set(document_ids)
    missing_relevant_ids = sorted({
        doc_id
        for _, relevant_ids in labeled_queries
        for doc_id in relevant_ids
        if doc_id not in document_id_set
    })
    if missing_relevant_ids:
        raise ValueError(
            "These labeled document IDs are absent from the current knowledge_chunks "
            f"collection: {', '.join(missing_relevant_ids[:10])}. "
            "Update the labels after ingestion or verify the IDs."
        )

    vectors = np.asarray(
        [chunk["vector_embedding"] for chunk in chunks],
        dtype=np.float32,
    )
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        from src.search import embedding_model
    except ImportError as error:
        raise RuntimeError(
            f"Missing evaluation dependency: {error.name}. Install project dependencies "
            "with 'python -m pip install -r requirements.txt'."
        ) from error

    for query, relevant_ids in labeled_queries:
        started_at = time.perf_counter()
        query_vector = embedding_model.encode(query)
        scores = cosine_similarity([query_vector], vectors)[0]
        ranked_indices = sorted(range(len(scores)), key=lambda index: -scores[index])
        ranked_ids = [document_ids[index] for index in ranked_indices]
        latency_ms = (time.perf_counter() - started_at) * 1000
        metrics = score_ranking(ranked_ids, relevant_ids)
        rows.append({
            "method": "sentence_transformer_cosine_baseline",
            "query": query,
            "relevant_document_count": len(relevant_ids),
            **{key: f"{value:.2f}" for key, value in metrics.items()},
            "query_latency_ms": f"{latency_ms:.2f}",
        })

    write_results(results_path, rows)
    metric_fields = RESULT_FIELDS[3:7]
    judgment_count = sum(len(relevant_ids) for _, relevant_ids in labeled_queries)
    unique_judgment_count = len({
        doc_id
        for _, relevant_ids in labeled_queries
        for doc_id in relevant_ids
    })
    summary_lines = [
        "Retrieval evaluation: existing Sentence Transformers cosine baseline",
        "Metrics are retrieval-quality measures, not ordinary classification accuracy.",
        "Precision@5, Recall@5, and nDCG@5 are shown as percentages; MRR is the "
        "reciprocal rank of the first relevant document across the full ranking.",
        "Latency measures query embedding plus full cosine ranking; model startup and MongoDB "
        "document loading are excluded.",
        f"Database: {database_name}",
        f"Indexed documents: {len(chunks)}",
        f"Labeled queries evaluated: {len(rows)}",
        f"Unlabeled query rows skipped: {unlabeled_count}",
        f"Positive query-document judgments: {judgment_count}",
        f"Unique judged relevant documents: {unique_judgment_count}",
    ]
    for field in metric_fields:
        average = sum(float(row[field]) for row in rows) / len(rows)
        summary_lines.append(f"Mean {field}: {average:.2f}%")
    average_latency = sum(float(row["query_latency_ms"]) for row in rows) / len(rows)
    summary_lines.append(f"Average query latency: {average_latency:.2f} ms")
    if len(rows) < 5:
        summary_lines.append(
            "Limitation: fewer than 5 labeled queries; treat these results as preliminary."
        )
    summary_lines.append(
        "Labels are manually judged but not certified exhaustive. Recall and nDCG are "
        "conditional on the supplied labels; missing relevant documents can distort scores."
    )
    write_summary(summary_path, "\n".join(summary_lines))

    print(f"Evaluated {len(rows)} labeled queries against {len(chunks)} documents.")
    print(f"CSV report: {results_path}")
    print(f"Summary: {summary_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate top-5 semantic retrieval against manual relevance labels."
    )
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    try:
        return run_evaluation(args.labels, args.output, args.summary)
    except (OSError, ValueError, RuntimeError) as error:
        message = f"Evaluation failed: {error}"
        write_results(args.output, [])
        write_summary(args.summary, message)
        print(message, file=sys.stderr)
        print(f"Created empty results CSV: {args.output}", file=sys.stderr)
        print(f"Summary: {args.summary}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
