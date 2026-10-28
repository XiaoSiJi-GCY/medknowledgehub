# 日志、Tracing 与指标

`app/observability/tracing.py` 定义节点 span 与 Prometheus 指标；`clients/models.py` 统计对话及嵌入的 Token 用量。LangGraph 每个节点都有独立 span，查询外层还有整体 span。

## 默认本地观察

API 日志记录 request_id、方法、响应状态与耗时，不记录 token 或请求正文。任务表保存阶段、尝试次数、状态和简洁失败原因。查询记录保存当前用户的检索路线、结果、引用和耗时，供反馈与评测使用。

`/metrics` 提供 medhub_queries_total、medhub_query_seconds、medhub_model_tokens_total。重排服务若不返回标准 Token 用量，就不伪造对应 Token 统计。Token 数不直接等于费用；计费还取决于服务商与模型。

## 可选 Langfuse

安装 observability 依赖后，配置 LANGFUSE_ENABLED、PUBLIC_KEY、SECRET_KEY 与 BASE_URL。默认关闭。启用后记录节点和 generation 的模型及用量信息；当前代码不主动上传完整问诊原文或资料正文。

本项目锁定 Langfuse Python SDK 3.x，使用其 span/generation 接口；新版云端和自托管版本的兼容性应按服务端情况核对。参考 [Langfuse SDK 文档](https://langfuse.com/docs/observability/sdk/overview)。没有配置真实项目凭据时，只能验证接入代码与本地指标，不能声称已上传云端轨迹。

## 学习实验

对同一个问题运行两次，观察 cache_hit、耗时和嵌入用量；再使用复杂问题观察 plan、retrieve、assess、retry 的节点顺序。区分队列等待、解析耗时、模型耗时与数据库查询耗时，避免把所有慢请求都归因于 LLM。
