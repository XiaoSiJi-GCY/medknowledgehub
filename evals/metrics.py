import math


def retrieval_metrics(ranked_ids, relevant_ids, k=5):
    ranked = list(dict.fromkeys(ranked_ids))[:k]
    relevant = set(relevant_ids)
    if not relevant:
        return {"recall_at_k": None, "mrr": None, "ndcg": None}
    recall = len(set(ranked) & relevant) / len(relevant)
    mrr = next((1 / index for index, item in enumerate(ranked, 1) if item in relevant), 0.0)
    dcg = sum(1 / math.log2(index + 1) for index, item in enumerate(ranked, 1) if item in relevant)
    ideal = sum(1 / math.log2(index + 1) for index in range(1, min(k, len(relevant)) + 1))
    return {"recall_at_k": recall, "mrr": mrr, "ndcg": dcg / ideal if ideal else 0.0}
