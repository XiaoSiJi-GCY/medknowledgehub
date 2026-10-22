"""Run real retrieval ablations; never synthesize a benchmark result."""

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import ROOT
from app.runtime import Runtime
from app.schemas import QueryRequest
from app.services.answers import Answers
from evals.metrics import retrieval_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["dense", "bm25", "hybrid", "rerank", "agentic"], default="rerank")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/datasets/retrieval.jsonl")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime, results = Runtime(), []
    try:
        user = runtime.identity.resolve(runtime.settings.service_token.get_secret_value())
        for line in args.dataset.read_text(encoding="utf-8").splitlines():
            case = json.loads(line)
            scope = runtime.kbs.scope(user)
            started, answer = time.perf_counter(), None
            if args.strategy == "agentic":
                answer = Answers(runtime).run(user, QueryRequest(query=case["query"], limit=args.limit))
                hits = answer["citations"]
            elif args.strategy in {"hybrid", "rerank"}:
                hits, _ = runtime.retriever.search(case["query"], scope, args.limit, rerank=args.strategy == "rerank")
            else:
                vector = runtime.models.embed([case["query"]])[0]
                dense, sparse = runtime.vectors.search(case["query"], vector, scope, args.limit)
                hits = runtime.retriever.hydrate(dense if args.strategy == "dense" else sparse, scope)
            titles = [hit["title"] for hit in hits]
            row = {
                "id": case["id"],
                "query": case["query"],
                "titles": titles,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                **retrieval_metrics(titles, case["relevant_titles"], args.limit),
            }
            if answer:
                row.update(
                    answer=answer["answer"],
                    retrieved_contexts=[hit["text"] for hit in hits],
                    route=answer["route"],
                    no_answer=answer["no_answer"],
                    route_correct=answer["route"] == case.get("expected_route"),
                    no_answer_correct=answer["no_answer"] == case.get("unanswerable", False),
                )
                if answer["sql_rows"]:
                    row["retrieved_contexts"].append(
                        "受控 SQL 查询结果：" + json.dumps(answer["sql_rows"], ensure_ascii=False)
                    )
            results.append(row)
            print(case["id"], row["latency_ms"], "ms", flush=True)
        metrics = {}
        for key in ("recall_at_k", "mrr", "ndcg", "route_correct", "no_answer_correct"):
            values = [row[key] for row in results if row.get(key) is not None]
            if values:
                metrics[key] = sum(values) / len(values)
        latencies = sorted(row["latency_ms"] for row in results)
        if latencies:
            metrics.update(
                p50_ms=statistics.median(latencies),
                p95_ms=latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            )
        report = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "strategy": args.strategy,
            "dataset": args.dataset.name,
            "samples": len(results),
            "k": args.limit,
            "models": {
                "chat": runtime.settings.model_name,
                "embedding": runtime.settings.embedding_model,
                "reranker": runtime.settings.rerank_model,
            },
            "metrics": metrics,
            "results": results,
            "scope": "Small manually labelled project corpus; document-title relevance, not clinical accuracy.",
        }
        output = args.output or ROOT / "artifacts/evals" / (args.strategy + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metrics, ensure_ascii=False), flush=True)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
