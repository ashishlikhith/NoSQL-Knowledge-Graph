import tempfile
import unittest
from pathlib import Path

from evaluate_retrieval import load_labels, score_ranking


class RetrievalMetricsTests(unittest.TestCase):
    def test_score_ranking_calculates_top_five_metrics(self):
        metrics = score_ranking(
            ["relevant-first", "irrelevant", "relevant-third"],
            ["relevant-first", "relevant-third"],
        )

        self.assertAlmostEqual(metrics["precision_at_5_percent"], 40.0)
        self.assertAlmostEqual(metrics["recall_at_5_percent"], 100.0)
        self.assertAlmostEqual(metrics["mrr_percent"], 100.0)
        self.assertAlmostEqual(metrics["ndcg_at_5_percent"], 100 * 1.5 / (1 + 1 / 1.584962500721156))

    def test_no_relevant_documents_retrieved_returns_zero(self):
        metrics = score_ranking(["other"], ["relevant"])

        self.assertEqual(metrics["precision_at_5_percent"], 0)
        self.assertEqual(metrics["recall_at_5_percent"], 0)
        self.assertEqual(metrics["mrr_percent"], 0)
        self.assertEqual(metrics["ndcg_at_5_percent"], 0)

    def test_mrr_uses_full_ranking_beyond_top_five(self):
        metrics = score_ranking(
            ["other"] * 5 + ["relevant"],
            ["relevant"],
        )

        self.assertAlmostEqual(metrics["mrr_percent"], 100 / 6)
        self.assertEqual(metrics["precision_at_5_percent"], 0)
        self.assertEqual(metrics["recall_at_5_percent"], 0)

    def test_load_labels_skips_unlabeled_rows_and_deduplicates_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            labels_path = Path(temporary_directory) / "labels.csv"
            labels_path.write_text(
                "query,relevant_doc_ids\n"
                "history,wiki_node_1; wiki_node_2;wiki_node_1\n"
                "geography,\n",
                encoding="utf-8",
            )

            labeled, unlabeled_count = load_labels(labels_path)

        self.assertEqual(labeled, [("history", ["wiki_node_1", "wiki_node_2"])])
        self.assertEqual(unlabeled_count, 1)


if __name__ == "__main__":
    unittest.main()
