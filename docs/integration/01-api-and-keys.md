# API、模型与 Key 统一清单

## 必需的外部凭据

当前配置共用硅基流动。**必需的外部密钥只有 OPENAI_API_KEY**。已有本机凭据已迁移，无需再发送到聊天中；确认账号余额及所选模型的调用权限即可。

| 用途 | 配置 | 当前值或填写方式 |
| --- | --- | --- |
| 主接口 | OPENAI_BASE_URL | https://api.siliconflow.cn/v1 |
| 模型 Key | OPENAI_API_KEY | 只填 care-suite/.env |
| 问诊抽取、知识回答 | MODEL_NAME | Qwen/Qwen3.5-9B |
| 向量化 | EMBEDDING_MODEL | BAAI/bge-m3，维度 1024 |
| 重排 | RERANK_MODEL | BAAI/bge-reranker-v2-m3 |
| 服务互访 | SERVICE_TOKEN | 本机迁移或随机生成，init 登记为只读身份 |
| 知识服务 | MEDHUB_API_URL | http://127.0.0.1:8010/api/v1 |

主模型、Embedding 和重排共用主 Key。SERVICE_TOKEN 无需向厂商申请，也不是患者登录 token；仅保存在后端，不写入页面或链接。

## 选配能力

| 能力 | 需要提供 | 空值时的行为 |
| --- | --- | --- |
| 独立报告视觉模型 | VISION_MODEL，必要时 VISION_BASE_URL、VISION_API_KEY | 复用主模型、主地址和主 Key；图像转录仍需所选模型及供应商支持图像输入 |
| 扫描件解析 | MINERU_API_URL，启用鉴权时再填 MINERU_API_KEY | 文本 PDF、Office 等照常解析，扫描件不能假定已解析 |
| Langfuse | LANGFUSE_ENABLED=true、LANGFUSE_BASE_URL、LANGFUSE_PUBLIC_KEY、LANGFUSE_SECRET_KEY | 本地日志和指标可用 |
| 独立向量服务 | EMBEDDING_BASE_URL | 主地址和主 Key；接口须兼容 OpenAI Embeddings |
| 独立重排服务 | RERANK_API_URL，完整 /rerank 地址 | 主地址的 /rerank，仍共用主 Key |

另一供应商若需要独立鉴权或不同协议，应扩展客户端，不能只改 URL。更换向量模型或维度后还需新建集合并重建索引。

## 不需要额外 API 的部分

PostgreSQL、Redis、Neo4j、Milvus 使用本机 Docker。数据库密码由配置生成，保存在 MedKnowledgeHub 自己的 .env。CarePilot 业务数据使用 SQLite。HTTP、SSE、MCP 不需要额外商业 Key。

当前预约使用项目内科室、医生与排班。以后接入真实医院时才需要医院授权 API、测试环境及字段协议，目前不用提供医院 Key。

## 修改顺序

编辑 care-suite/.env，然后停止并重启两个 API 和 Worker。SERVICE_TOKEN 更改后先 init 登记新值，再 start；当前 bootstrap 不自动撤销旧 token，安全轮换时还需撤销旧服务 token 记录。修改已有数据库密码时，数据库内密码与配置也必须同步。

排查冲突先检查进程环境变量，它们优先于共享文件。排查只输出“是否配置”和模型名称，不打印密钥。
