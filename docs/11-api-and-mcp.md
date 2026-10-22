# HTTP API、SSE 与 MCP

HTTP 路由在 `app/api/routes.py`，请求模型在 `app/schemas.py`。接口均使用 `/api/v1` 前缀；资源读取需要 Bearer token，存活和就绪检查除外。

| 接口组 | 主要入口 |
| --- | --- |
| 身份 | POST `/auth/register`、`/auth/login`、`/auth/logout`，GET `/auth/me` |
| 成员 | GET/POST `/users` |
| 知识库 | GET/POST `/knowledge-bases`，PUT/DELETE `/{id}`，grants 授权接口 |
| 文档 | POST/GET `/documents`，版本、对比与停用接口 |
| 任务 | GET `/tasks`、`/tasks/{id}`，POST `/{id}/retry` |
| 检索 | POST `/retrieval/search`；GET `/knowledge/search` 兼容 CarePilot |
| 问答 | POST `/answers`、`/answers/stream` |
| 原文与反馈 | GET `/sources/{id}`、`/queries`，POST `/feedback` |

打开 `/docs` 查看当前实际参数与 Schema。错误信息不回显数据库连接串或模型密钥。

## SSE 事件

`stage` 提供节点名与检索轮数，`answer_delta` 提供经过校验的最终文本片段，`done` 返回完整回答、引用、路线、耗时和 query_id；失败发送 `error`。前端不应把 TCP 连接结束当作成功，必须收到 done。

## MCP 服务

启动 `python -m app.mcp_server`，通过 stdio 提供六个工具：list_knowledge_bases、search_knowledge、read_source、query_relations、query_structured、compare_document_versions。

服务启动时使用 `MEDHUB_MCP_TOKEN` 或 `.env` 的 SERVICE_TOKEN 绑定一个身份。每个进程只代表这个身份；多用户部署应为不同身份隔离进程或扩展正式鉴权传输。工具不能接收客户端伪造的 tenant_id/role，也不开放知识库写操作。

MCP 2.x 的 `MCPServer` 与早期 `FastMCP` API 不同，本项目以锁定依赖及 `test_mcp.py` 的在进程内真实客户端连接为准。MCP 不等于 HTTP 路由的别名，但两者复用同一业务服务与权限规则。
