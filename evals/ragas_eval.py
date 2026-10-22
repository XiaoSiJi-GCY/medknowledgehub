"""Optional independent LLM-judge evaluation of an actual agentic evaluation report."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/evals/ragas.json"))
    args = parser.parse_args()
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness
    from ragas.run_config import RunConfig
    from langchain_openai import ChatOpenAI
    from app.core.config import get_settings

    settings = get_settings()
    chat = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        temperature=0,
        timeout=120,
        max_retries=1,
        extra_body={"enable_thinking": False},
    )
    report = json.loads(args.report.read_text(encoding="utf-8"))
    samples = [
        SingleTurnSample(user_input=row["query"], response=row["answer"], retrieved_contexts=row["retrieved_contexts"])
        for row in report["results"]
        if row.get("answer") and row.get("retrieved_contexts")
    ]
    if not samples:
        raise ValueError("请先运行 --strategy agentic，生成包含回答与上下文的报告")
    judge = LangchainLLMWrapper(chat)
    result = evaluate(
        EvaluationDataset(samples=samples),
        metrics=[Faithfulness(llm=judge)],
        llm=judge,
        run_config=RunConfig(max_workers=1, timeout=120, max_retries=1),
        raise_exceptions=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = result.to_pandas().to_dict(orient="records")
    args.output.write_text(
        json.dumps(
            {"judge_model": settings.model_name, "metric": "faithfulness", "results": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(result)


if __name__ == "__main__":
    main()
