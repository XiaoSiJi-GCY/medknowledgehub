# 评测：指标、消融与失败案例

测试负责程序行为，检索评测负责排序效果，LLM judge 负责部分答案质量判断。三者不能互相替代。

## 当前数据与口径

`evals/datasets/retrieval.jsonl` 包含八条人工标注问题，标注相关文档标题、预期路线与是否无答案。初始语料只有五份资料；这里按文档标题去重计算相关性，而不是逐 Chunk 的医学相关性标注。后续应扩充独立测试集、同义问法、跨库问题、过期资料与拒答样例。

## 检索指标

`evals/metrics.py` 实现 Recall@K、MRR 和二值相关性的 nDCG。无相关文档标注的样例不进入这些指标的平均值。`evals.run` 记录每条结果、模型配置、延迟和输出文件，默认写入 artifacts/evals。

```powershell
python -m evals.run --strategy dense
python -m evals.run --strategy bm25
python -m evals.run --strategy hybrid
python -m evals.run --strategy rerank
python -m evals.run --strategy agentic
```

前四种用于检索消融；agentic 额外执行路由与回答，记录 route_correct、no_answer_correct 和回答上下文。缓存命中与模型延迟会影响测量，不能将小样本 p95 当作生产 SLO。

## RAGAS

```powershell
py -3.11 -m venv .venv-eval
.\.venv-eval\Scripts\python.exe -m pip install -r evals/requirements.txt
.\.venv-eval\Scripts\python.exe -m evals.ragas_eval artifacts/evals/agentic.json
```

RAGAS 使用独立 `.venv-eval`，避免其 LangChain 0.3 依赖与主应用的 LangChain 1.x 冲突。无需在评测环境安装本项目运行依赖，模块从项目根目录读取配置。

该入口使用真实 agentic 报告构造 EvaluationDataset，调用配置模型评估 Faithfulness。它会产生额外 API 用量。当前判断模型与生成模型默认相同，存在共同偏差，适合学习与误差分析；正式评测建议使用独立判断模型并辅以人工审核。

SQL 的计算结果额外作为上下文记录，避免把数据库实际计算出的数量误认为凭空生成。RAGAS 得分仍不等于临床准确率。接口依据：[RAGAS 0.3.9 评测文档](https://docs.ragas.io/en/v0.3.9/getstarted/evals/)。

## 如何记录一个改进

固定资料版本、测试集与模型，再只改变一个因素，例如关闭重排或改变 Top K。保留逐题结果和失败样例，再计算差异。当前语料上的满分很容易受到资料规模与标注粒度影响，不应写为系统总体准确率。

权限隔离以独立 API/回归测试验证，不通过普通 Recall 指标推导。真实运行与测试记录见 [验证记录](17-validation.md)。
