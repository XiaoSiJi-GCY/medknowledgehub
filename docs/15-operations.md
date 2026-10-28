# 运维与故障排查

## 先判断故障在哪一层

| 现象 | 优先检查 |
| --- | --- |
| 页面打不开 | Streamlit 是否监听 8510，端口是否被占用 |
| 页面能开但登录失败 | API 是否监听 8010，数据库迁移是否执行，账号是否属于本项目 |
| 任务一直 queued | Celery Worker、Redis 连接、队列 medhub-ingestion |
| 任务在 embedding 失败 | 模型密钥、嵌入权限、维度、文本长度 |
| 扫描 PDF 失败 | MinerU 地址、鉴权、V1 输出格式；没有配置时应明确失败 |
| 无检索结果 | 权限、active_version_id、生效与失效日期、版本是否 ready |
| 图检索无结果 | 是否抽取到原文关系、Neo4j 可用、问题实体是否匹配 |
| SQL 被拒绝 | 查询是否超出开放表、字段、函数或只读范围 |
| 回答没有引用 | 证据不足或引用检查失败，检查原文而不是放宽为随意回答 |

## 运行状态

`docker compose ps` 查看四个基础服务。`python -m scripts.check_environment` 检查数据库连接；`/health` 只表示 API 进程存活，`/health/ready` 表示基础依赖可连接。队列 Worker 状态还需查看任务与 Worker 日志。

普通重启使用 `docker compose stop/start`；删除 volume 会删除数据库和索引，不能作为日常排错手段。代码修改后重启 API 和 Worker；只刷新浏览器不会重载已经运行的后端 Python 模块。

## 索引重建与清理

原始资料和解析产物可用于重建。对失败任务可调用 `/tasks/{id}/retry`。已发布文档重建可运行 `python -m scripts.reindex <document_id>` 或调用 `/documents/{id}/reindex`，它先构建替换版本，完成后再切换，保留旧版本可用性。旧投影清理由 Celery 的 medhub.cleanup 执行；清理之前旧内容已经被当前版本范围排除。当前没有无限自动重试和全局分布式事务。

## 备份范围

保留 PostgreSQL 数据、原始资料、必要解析产物及本机配置的安全副本；Milvus、Neo4j 可根据当前文档重建，仍可按成本做备份。Redis 不是文档权限的唯一来源。真实密钥、用户数据与数据库卷不应提交 Git。

## 公开部署前的工程工作

当前 Compose 面向本机学习。公网部署需要 TLS、访问入口、账号与限流策略、备份、监控告警、数据保留政策及资源容量评估。初始资料与代码测试不构成医疗服务上线依据。
