from evals.metrics import retrieval_metrics


def test_metrics_handle_order_duplicates_and_no_relevance_labels():
    result = retrieval_metrics(["wrong", "right", "right"], ["right"], 5)
    assert result["recall_at_k"] == 1 and result["mrr"] == 0.5
    assert 0 < result["ndcg"] < 1
    assert retrieval_metrics([], [], 5)["mrr"] is None
