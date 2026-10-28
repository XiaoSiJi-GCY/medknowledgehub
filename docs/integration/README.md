# Care Suite：CarePilot 与 MedKnowledgeHub 联合运行

> 本页是联合运行手册的仓库快照。可公开的启动脚本与配置模板位于 [examples/care-suite](../../examples/care-suite/)。请将该目录复制到两个项目的同级位置并命名为 care-suite，再执行下列命令。不要直接在 docs 目录运行。

> 联合验证对应本机已接入的 CarePilot 版本。若公开 CarePilot 仓库尚未同步相应改动，需要按集成文档装配客户端和工作流；MedKnowledgeHub 自身可以独立运行。

CarePilot 负责问诊状态、门诊推荐、报告转录和人工确认预约；MedKnowledgeHub 负责资料版本、检索与带引用回答。两个项目保留独立服务和虚拟环境，本目录统一配置、启动与联调。

## 本机运行

先打开 Docker Desktop，在本目录依次使用：

```powershell
.\run.ps1 start
.\run.ps1 status
.\run.ps1 stop
```

| 页面 | 地址 | 账号 |
| --- | --- | --- |
| 就医助手 | http://127.0.0.1:8501 | 原 CarePilot 账号，或在页面注册 |
| 知识中台 | http://127.0.0.1:8510 | medknowledgehub/.env 的管理员账号 |
| 业务 API 文档 | http://127.0.0.1:8000/docs | 患者 token |
| 知识 API 文档 | http://127.0.0.1:8010/docs | 知识账号或服务 token |

stop 只停止本脚本启动且 PID、创建时间一致的进程，保留容器和数据。PyCharm 手动启动的进程需手动停止。修改共享 Key 后先 stop 再 start。

执行策略阻止 ps1 时，可直接调用同目录 suite.py，解释器使用 MedKnowledgeHub 的 .venv。

## 首次准备

先按两个项目 README 建立各自 .venv、安装依赖并创建项目 .env，再运行：

```powershell
..\medknowledgehub\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\medknowledgehub\.venv\Scripts\python.exe configure.py
# 编辑 care-suite/.env，填写自己的 OPENAI_API_KEY
.\run.ps1 init
.\run.ps1 start
.\run.ps1 seed
```

init 启动基础容器、迁移数据库、初始化索引并登记服务身份；seed 导入来源清单。没有语料时会明确返回资料不足。

## 学习与验证

[API 与 Key 清单](01-api-and-keys.md) → [集成架构与源码](02-integration.md) → [验证记录](03-validation.md)。

描述“咳嗽持续三周”，再问“需要注意什么？”，查看引用及“本轮知识依据”；再问“应该挂什么科？”，查看可预约科室。挂号使用 CarePilot 的实际目录与号源。

run.ps1 test 在各自解释器中运行回归；run.ps1 smoke 使用真实知识库和模型，会产生 API 用量并创建联调账号与会话。

## 目录与配置

同级的 carepilot、medknowledgehub 保留源码、数据库配置和虚拟环境。care-suite 包含共享 .env、模板、configure.py、suite.py、run.ps1、smoke_live.py、docs 及本机 .runtime。

配置优先级：Settings 显式参数 > 进程环境变量 > care-suite/.env > 项目自己的 .env > 默认值。CARE_SUITE_ENV_FILE 可指定共享文件；测试通过 _env_file=None 隔离本机设置。

configure 首次导入旧配置，MedKnowledgeHub 的模型配置优先；以后保留共享文件的编辑。原项目配置备份为 .env.before-suite。共享字段移至本目录，数据库密码、管理员账号和 SQLite 路径留在各自项目。

密钥、备份、原始数据和 .runtime 不提交到 Git。接入代码只转发当前问题、有限主诉与症状变化，不转发患者账号、完整对话、完整病史、预约和报告文件。查询背景仍可能含用户输入的敏感内容，知识服务会记录查询。

默认联合运行采用本机 Python 和 Docker 数据库。两边 Compose 也增加了可选共享 env_file；完整应用容器部署参考各自文档，避免与本机进程争用端口。配置校验不能代替完整容器联调。
