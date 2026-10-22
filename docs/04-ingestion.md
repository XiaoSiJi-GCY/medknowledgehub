# 文档解析、结构切分与异步入库

从 `app/api/routes.py` 的 `/documents` 开始阅读，再看 `Documents.upload()`、`IngestionPipeline.run()`、`parsers.py` 和 `chunking.py`。

## 支持格式与定位

| 格式 | 解析方式 | 保留信息 |
| --- | --- | --- |
| 文本 PDF | PyMuPDF blocks | 页码、bbox、块文本 |
| 扫描 PDF | 已配置的 MinerU V1 服务 | 返回的 Markdown；当前适配不承诺保留坐标 |
| Markdown/TXT/HTML | 文本或 HTML 清理 | 标题路径与正文；HTML 去除脚本、样式 |
| DOCX | python-docx | 按正文顺序的段落与表格、标题信息 |
| XLSX | openpyxl | 工作表名称、表格行与已有缓存值 |
| JSON | 受控 records 格式 | name/category/department/value/unit/description |

Office 文件限制解压总大小；PDF 检查文件头。当前文件上限默认 20 MiB，正文上限 30 万字符。扫描 PDF 无正文且没有配置 MinerU 时会明确失败，不将空文档标成入库成功。Excel 公式不会在服务器重新计算。

## 从 Block 到 Chunk

`parse()` 输出统一 Block，`chunk_blocks()` 保存标题路径和父级正文，普通文本按长度与重叠切成子块，表格使用较大块。每个 Chunk 有版本内的稳定位置与确定性 ID。PDF 页码和 bbox 随子块保留；普通 Markdown 没有页码，不会编造页码。

当前长表格仍按较大的文本窗口处理，复杂跨页表头、合并单元格及精确 DOCX 页码需要更专门的解析能力。原始文件和解析 JSON 始终保留，便于定位解析误差。

## 异步状态与失败

API 先持久化 Document、Version、IngestionTask，再提交 Celery。任务阶段包括 parsing、chunking、embedding、vector_index、graph_index、publish。客户端通过 `/tasks` 读取状态，无需保持上传连接。

任务以数据库条件更新领取，重复投递不会重复发布；失败保存阶段与简洁原因。网络等执行异常可有限重试，非法文件需修正输入。超过 30 分钟未更新的 processing 任务可重新领取。只有所有必要索引写入成功后才发布新版本，失败更新不替换旧有效版本。

同一文档下，内容与来源元数据相同的上传会复用版本；内容或元数据变化创建新版本。不同逻辑文档可以拥有相同正文。

## MinerU 配置

设置 `MINERU_API_URL` 指向自托管 V1 根地址，必要时配置 `MINERU_API_KEY`。适配器使用 `/v1/file_parse`，只向配置的源发送凭据，不跟随带鉴权的跨站跳转。响应没有可用 Markdown 时明确报错。尚未配置服务的本机只能验证普通文本解析与适配器协议测试，不能声称扫描件已实测。

接口依据：[MinerU V1 HTTP API](https://opendatalab.github.io/MinerU/usage/http_api/)。Celery 任务语义参考[官方任务文档](https://docs.celeryq.dev/en/stable/userguide/tasks.html)。

## 动手验证

制作两页 PDF，分别插入不同文字，上传后展开原文位置。再上传相同内容，比较版本 ID；修改一段后上传为新版本。故意停止模型服务进行更新，检查任务失败时旧版本能否继续检索。相关测试：`test_parsers.py` 和 `test_lifecycle.py`。
