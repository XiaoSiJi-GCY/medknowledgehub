# 源码目录索引

此索引列出实际交付文件，省略虚拟环境、密钥、运行产物及空的包标记。目录中每个模块的职责见 [架构与源码映射](01-architecture.md)。

```text
medknowledgehub/
├── .github/
│   └── workflows/
│       └── ci.yml
├── .streamlit/
│   └── config.toml
├── app/
│   ├── agents/
│   │   ├── graph.py
│   │   └── state.py
│   ├── api/
│   │   └── routes.py
│   ├── clients/
│   │   ├── mineru.py
│   │   └── models.py
│   ├── core/
│   │   ├── config.py
│   │   └── errors.py
│   ├── ingestion/
│   │   ├── chunking.py
│   │   ├── parsers.py
│   │   └── pipeline.py
│   ├── observability/
│   │   └── tracing.py
│   ├── retrieval/
│   │   ├── context.py
│   │   ├── fusion.py
│   │   ├── service.py
│   │   └── sql.py
│   ├── services/
│   │   ├── answers.py
│   │   ├── documents.py
│   │   ├── identity.py
│   │   └── knowledge_bases.py
│   ├── storage/
│   │   ├── cache.py
│   │   ├── database.py
│   │   ├── files.py
│   │   ├── graph.py
│   │   └── milvus.py
│   ├── workers/
│   │   └── celery_app.py
│   ├── main.py
│   ├── mcp_server.py
│   ├── models.py
│   ├── runtime.py
│   └── schemas.py
├── data/
│   ├── samples/
│   │   ├── cough.md
│   │   ├── departments.json
│   │   ├── lab-results.md
│   │   ├── shingles.md
│   │   └── stroke.md
│   └── source_manifest.json
├── deploy/
│   └── embedEtcd.yaml
├── docs/
│   ├── images/
│   │   └── architecture.svg
│   ├── 00-learning-path.md
│   ├── 01-architecture.md
│   ├── 02-quickstart.md
│   ├── 03-auth-and-permissions.md
│   ├── 04-ingestion.md
│   ├── 05-storage-and-versions.md
│   ├── 06-hybrid-retrieval.md
│   ├── 07-agentic-rag.md
│   ├── 08-graph-rag.md
│   ├── 09-sql-rag.md
│   ├── 10-context-and-citations.md
│   ├── 11-api-and-mcp.md
│   ├── 12-carepilot-integration.md
│   ├── 13-evaluation.md
│   ├── 14-observability.md
│   ├── 15-operations.md
│   ├── 16-interview-guide.md
│   ├── 17-validation.md
│   └── source-tree.md
├── evals/
│   ├── datasets/
│   │   └── retrieval.jsonl
│   ├── metrics.py
│   ├── ragas_eval.py
│   ├── requirements.txt
│   └── run.py
├── integrations/
│   └── carepilot_client.py
├── migrations/
│   ├── versions/
│   │   ├── 527bcdd315fe_knowledge_base_archival_and_effective_.py
│   │   └── 73856ad42c5b_initial_metadata_schema.py
│   ├── env.py
│   └── script.py.mako
├── scripts/
│   ├── bootstrap.py
│   ├── check_environment.py
│   ├── configure.py
│   ├── import_corpus.py
│   ├── reindex.py
│   ├── render_architecture.py
│   └── smoke_live.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_lifecycle.py
│   ├── test_mcp.py
│   ├── test_metrics.py
│   ├── test_mineru.py
│   ├── test_parsers.py
│   ├── test_permissions.py
│   ├── test_rag.py
│   └── test_sql.py
├── ui/
│   └── streamlit_app.py
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── README.md
├── alembic.ini
├── compose.yaml
├── pyproject.toml
├── requirements-lock.txt
└── run.ps1
```
