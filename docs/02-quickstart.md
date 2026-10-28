# 快速开始、PyCharm 与运行方式

## 环境要求

使用 Python 3.11 和能启动 Linux 容器的 Docker Desktop。四个基础服务会占用一定内存；本机开发建议给 Docker 分配足够资源。当前 Compose 只绑定回环地址，不自动向局域网开放。

在 PyCharm 中选择“打开”，打开 `medknowledgehub` 根目录。解释器选择 `.venv/Scripts/python.exe`；运行配置的工作目录也设为项目根目录。不要把 CarePilot 的虚拟环境当成本项目解释器。

## 首次安装

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,observability]"
.\.venv\Scripts\python.exe -m scripts.configure
```

`configure` 只在 `.env` 不存在时创建文件，生成独立数据库密码、管理员密码和服务 token。随后自行填写 `OPENAI_API_KEY`。请使用自己的模型服务凭据；仓库只包含配置模板。

`MODEL_NAME` 用于对话，`EMBEDDING_MODEL` 用于向量化，`RERANK_MODEL` 用于精排。默认三者使用同一 API 提供商。可单独设置 `EMBEDDING_BASE_URL` 和 `RERANK_API_URL` 接入其他兼容服务；更改向量模型或维度后需新建索引集合并重建资料。

## 启动基础服务并初始化

```powershell
docker compose up -d postgres redis neo4j milvus
.\.venv\Scripts\python.exe -m scripts.bootstrap
.\.venv\Scripts\python.exe -m scripts.check_environment
```

`bootstrap` 执行 Alembic 迁移，建立 Milvus schema 和 BM25 Function，建立 Neo4j 唯一约束，创建管理员与只读服务身份。它可以重复执行，不会重置已有密码或文档。

## 启动三个进程

| 进程 | 命令 | 用途 |
| --- | --- | --- |
| API | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010` | 接收请求、验证身份和执行问答 |
| Worker | `python -m celery -A app.workers.celery_app:celery_app worker --pool=solo --loglevel=INFO` | 执行文档解析、向量化与索引任务 |
| 页面 | `python -m streamlit run ui/streamlit_app.py --server.address 127.0.0.1 --server.port 8510` | 知识库、资料和问答界面 |

表中 `python` 均指本项目解释器。Windows 不激活环境时可将其替换为 `.\.venv\Scripts\python.exe`。`run.ps1` 支持对应快捷参数，执行策略受限时直接使用 Python 命令。

## 导入初始资料并登录

```powershell
.\.venv\Scripts\python.exe -m scripts.import_corpus --wait
```

导入任务会进入 Celery，因此 Worker 必须运行。需要排查队列时，可以用 `--inline` 在当前进程执行同一条入库链路。它仍使用真实模型和数据库。

页面：[http://127.0.0.1:8510](http://127.0.0.1:8510)。接口说明：[http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs)。管理员账号查看 `.env` 的 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`。账号体系与 CarePilot 独立。

## 完整容器方式

```powershell
docker compose --profile app up -d --build
docker compose exec api python -m scripts.bootstrap
docker compose exec api python -m scripts.import_corpus --wait
```

容器中 API 和 Worker 使用服务名访问数据库，共享 `data` 目录；页面通过 `http://api:8010` 请求 API。首次构建需下载 Python 镜像与依赖。更改源码后需要重新构建镜像；本地 Python 方式则重启对应进程。

停止本地进程用 Ctrl+C。`docker compose stop` 停止容器并保留数据卷；不要为了普通重启删除数据卷。完整排错见 [运维手册](15-operations.md)。
