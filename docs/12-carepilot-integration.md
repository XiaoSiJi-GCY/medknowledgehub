# 与 CarePilot 的对接

MedKnowledgeHub 独立部署，当前不自动改动 CarePilot 的环境或数据库。适配器位于 `integrations/carepilot_client.py`，保留 `search(query, limit=...)` 与 `close()` 接口，返回 id、title、url、summary、score。

## 接入位置

1. 将适配器放到 CarePilot 的 services 中。
2. 在 CarePilot 配置增加知识服务地址和服务 token；地址示例为 `http://127.0.0.1:8010/api/v1`。
3. 在 CarePilot 的 `app/main.py` 初始化客户端，将其注入原有 ConsultationService。
4. 保留原来的超时与来源卡降级策略，分别测试知识服务正常、无结果和不可用时的问诊行为。

```python
from integrations.carepilot_client import MedKnowledgeHubClient

knowledge = MedKnowledgeHubClient(
    base_url="http://127.0.0.1:8010/api/v1",
    token="从本机环境变量读取服务凭据",
)
sources = knowledge.search("咳嗽持续超过三周", limit=2)
```

代码示例中的 token 是说明文字，实际使用环境变量读取，不能提交真实值。

## 两个项目各自负责什么

CarePilot 组织问诊状态、风险提示、报告转录与人工确认预约；MedKnowledgeHub 组织资料、检索、引用、权限和版本。直接接入检索 API 时，CarePilot 使用的是证据片段，不会自动得到完整 RAG 回答；要接入 `/answers`，需单独设计问诊摘要与知识解释的呈现方式。

当前 0.12 阈值对应重排相关度，与 CarePilot 原来余弦相似度 0.58 的含义不同。替换检索实现时不能沿用旧阈值并假设可比。

## 验证

`smoke_live.py` 检查兼容 HTTP 接口；`tests/test_api.py` 验证鉴权。正式切换时还应复测用户会话隔离、急症分支及预约人工确认。两个项目使用不同端口：CarePilot 8000/8501，MedKnowledgeHub 8010/8510。
