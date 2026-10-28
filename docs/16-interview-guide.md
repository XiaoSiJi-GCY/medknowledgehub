# 项目讲解与面试追问

先讲清楚用户问题，再讲执行链路和技术取舍。下面的描述只对应当前代码，不包含未经测量的提升比例。

## 一分钟介绍

MedKnowledgeHub 是独立的医疗知识管理与 Agentic RAG 服务。它将文档上传、异步解析、结构分块和版本索引连接起来，通过 LangGraph 为不同问题选择混合检索、图关系查询或受控 SQL，再组织有来源的回答。PostgreSQL 保存权限和文档真值，Milvus 与 Neo4j 保存可重建投影，Redis 提供队列与缓存。系统通过 HTTP 和 MCP 开放能力，并提供 CarePilot 的检索适配器。

## 需要能定位的源码

| 面试问题 | 代码与回答重点 |
| --- | --- |
| 为什么用 LangGraph？ | `agents/graph.py`：规划、评估、有限次补充检索与可观察终止 |
| 混合检索为什么不直接相加分数？ | `fusion.py`：Dense/BM25 尺度不同，RRF 使用排名；重排重新比较问题与正文 |
| 如何避免撤权后命中缓存？ | `knowledge_bases.py`、`retrieval/service.py`：可信身份、范围签名、命中后回表校验 |
| 文档更新一半失败会怎样？ | `ingestion/pipeline.py`：先写投影后发布，旧版本继续有效，失败状态可重试 |
| 图关系怎么保证出处？ | `clients/models.py`、`storage/graph.py`：原文实体、quote、Chunk 和版本绑定；不夸大语义正确性 |
| Text-to-SQL 怎么防止越界？ | `retrieval/sql.py`：AST 白名单、权限子查询、只读事务、超时和行数限制 |
| 引用校验是否等于回答正确？ | `agents/graph.py`：只能证明引文存在和来源绑定；语义支持需另行评测 |
| 怎样证明性能或质量提升？ | `evals/`：固定语料、模型和测试集，做消融并保留逐题结果 |
| CarePilot 如何复用？ | `integrations/carepilot_client.py`：search 接口、来源卡字段、鉴权和超时 |
| 当前还有哪些限制？ | 小语料、候选图关系、单视图 SQL、可选外部解析与 Tracing，见验证记录 |

## 演示顺序

先展示一份资料的任务与版本，再提一个有证据的问题并定位原文；接着展示一个无答案问题和受限知识库的访问差异；最后展示科室数量 SQL 及图路径，解释计算与生成的不同来源。

简历可以写已实现的模块和真实验证方式；不要把小样本标题级 Recall 写成临床准确率，也不要把未配置的 MinerU/Langfuse 或尚未验证的业务部署写成已完成业务上线。

## 2026-10-28 联合运行补充

CarePilot 的检索、带引用问答和原文读取已经接入。服务边界、共享配置和真实验证见 [联合文档](integration/02-integration.md)。
