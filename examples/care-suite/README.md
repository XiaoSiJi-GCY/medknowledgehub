# 联合运行脚本模板

将本目录复制到 medknowledgehub 与 carepilot 两个项目的同级目录，命名为 care-suite。源码不包含真实 .env、数据库、日志或账号。先分别准备两个项目的虚拟环境，再按 [联合运行手册](../../docs/integration/README.md) 配置。

公开 CarePilot 仓库的具体版本需要具备集成文档所列客户端、知识状态字段和工作流分支；本模板不会自动修改 CarePilot 源码。MedKnowledgeHub 可以按仓库根 README 独立运行。
