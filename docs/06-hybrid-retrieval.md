# 混合检索：Dense、BM25、RRF 与 Reranker

入口是 `app/retrieval/service.py` 的 `Retriever.search()`；数据库实现位于 `app/storage/milvus.py`，融合算法位于 `fusion.py`，模型接口位于 `clients/models.py`。

## 为什么组合两种召回

Dense 用 BGE-M3 表达语义相近程度，适合表达变化；BM25 根据词项命中与语料统计排序，适合疾病名称、缩写和明确关键词。二者的原始分数不是同一尺度，不能直接相加。

项目在 Milvus 建集合时配置文本 analyzer 和 BM25 Function，让插入的正文自动产生稀疏向量。Dense 字段使用 COSINE，稀疏字段使用 BM25。中文分词采用 jieba tokenizer。实现依据：[Milvus 全文检索](https://milvus.io/docs/full-text-search.md)。

## 实际调用顺序

```text
权限范围 → 查询向量 → Dense/BM25 召回 → RRF → PostgreSQL 校验 → BGE-Reranker → Top K
```

多条查询先批量向量化，再最多三路并行召回。每条查询的两种召回都使用相同空间、知识库与版本过滤。RRF 对每个排名贡献 `1/(60+rank)`，合并后最多取 30 个候选精排。

Reranker 直接比较问题与正文，不使用已被平均融合的原始分数。最终 score 是重排模型相关度，不能解释为诊断概率。低于配置阈值的片段不会进入生成上下文。

## 缓存与可观察结果

`debug.dense`、`debug.bm25` 保存经过授权校验的候选 ID，`cache_hit` 说明是否复用结果。向量与重排模型改变后需要注意集合维度、索引重建和缓存版本。Milvus 中不存在的 ID、错误空间或旧版本的 Chunk 会在回表校验中剔除。

## 怎么比较效果

分别运行 `evals.run --strategy dense/bm25/hybrid/rerank`。相同语料与标注下比较 Recall@K、MRR、nDCG 和延迟，再判断融合或重排是否值得。当前小语料的高分不能外推到大规模指南库。

重排调用依据：[硅基流动 Rerank API](https://docs.siliconflow.cn/docs/api/rerank-post)。动手阅读 `test_permissions.py` 中故意返回跨空间 ID 的索引，观察为什么仍不能进入结果。
