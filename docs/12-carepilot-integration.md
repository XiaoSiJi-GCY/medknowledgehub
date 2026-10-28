# 与 CarePilot 联合接入

两个服务现已接通。统一启动和共享配置见 [Care Suite](integration/README.md)，需要的 API 与 Key 见 [配置清单](integration/01-api-and-keys.md)，源码链路见 [集成架构](integration/02-integration.md)。

实际适配器位于 carepilot/app/services/medknowledgehub.py，由 app/services/knowledge.py 工厂按 KNOWLEDGE_BACKEND 创建，并在 app/main.py 注入。医学问答调用 /api/v1/answers，摘要及科室分支调用 /api/v1/knowledge/search；原文通过 CarePilot 已登录接口代理读取。急症分支不等待检索。

共享模型与服务凭据在 care-suite/.env；各项目数据库和账号独立保留。患者登录 CarePilot，后台以知识服务 viewer 身份查询。当前为单个 CarePilot 实例共享一个被授权的知识空间，不是自动按患者建立知识空间。

医学解释使用混合检索；完整自动路由、图关系、SQL 和 MCP 仍在知识中台。预约以 CarePilot 业务目录、医生与号源为准。远端重排相关度阈值默认 0.12，不能与旧本地余弦阈值 0.58 混用。

知识服务失败时明确提示，保留就诊字段、科室导航和预约功能。实际验证见 [联合验证记录](integration/03-validation.md)。独立检索示例仍保留在 integrations/carepilot_client.py；完整集成以 CarePilot 适配器与对应回归测试为准。

## 独立客户端使用

仓库内 integrations/carepilot_client.py 不依赖 CarePilot 内部 Settings，可直接复制复用：

```python
import os
from integrations.carepilot_client import MedKnowledgeHubClient

client = MedKnowledgeHubClient(
    base_url=os.getenv("MEDHUB_API_URL", "http://127.0.0.1:8010/api/v1"),
    token=os.environ["SERVICE_TOKEN"],
)
try:
    result = client.answer("咳嗽持续超过三周需要注意什么？")
    print(result["answer"])
finally:
    client.close()
```

search 返回来源卡；answer 返回 answer、sources、status；source 按片段编号读取已授权原文。示例的输出是知识资料解释，不会创建预约。完整工作流接入还包括 CarePilot 的意图分流、状态恢复和急症优先，不能只替换类名就认为全部接入完成。
