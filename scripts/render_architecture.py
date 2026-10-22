"""Generate the editable repository architecture SVG without a rendering service."""

from html import escape
from app.core.config import ROOT


def main():
    width, height = 1200, 1270
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f2f6fb"/>',
        '<style>text{font-family:"Microsoft YaHei",Arial,sans-serif;fill:#163047} .muted{fill:#48647b}</style>',
    ]

    def text(value, x, y, size=19, bold=False):
        svg.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{size}" font-weight="{700 if bold else 400}">{escape(value)}</text>'
        )

    def rect(x, y, w, h, fill):
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="#91adc3"/>')

    def layer(y, title, cards):
        rect(30, y, 1140, 156, "#dceaf7")
        text(title, 600, y + 31, 23, True)
        n = len(cards)
        cw = (1100 - (n - 1) * 16) / n
        for index, lines in enumerate(cards):
            x = 50 + index * (cw + 16)
            rect(x, y + 50, cw, 88, "#ffffff")
            for line_index, line in enumerate(lines):
                text(line, x + cw / 2, y + 77 + line_index * 24, 18 if line_index else 20, line_index == 0)

    text("MedKnowledgeHub v1.0 系统架构", 600, 47, 32, True)
    text("知识管理 · 有限次 Agentic RAG · 原文证据与权限", 600, 80, 19)
    layer(
        110,
        "交互与接入",
        [
            ("Streamlit · 8510", "知识库 / 资料 / 问答", "ui/streamlit_app.py"),
            ("CarePilot / HTTP", "来源检索与证据卡", "integrations/carepilot_client.py"),
            ("MCP · stdio", "六个只读工具", "app/mcp_server.py"),
        ],
    )
    layer(
        305,
        "API 与身份边界 · FastAPI 8010",
        [
            ("HTTP / SSE", "文档、任务、检索、问答", "app/api/routes.py"),
            ("可信身份与范围", "空间 / 角色 / 知识库授权", "services/identity.py / knowledge_bases.py"),
        ],
    )
    layer(
        500,
        "编排与处理",
        [
            ("异步入库 · Celery", "解析 → 分块 → 索引 → 发布", "ingestion/pipeline.py"),
            ("Agentic RAG · LangGraph", "规划 → 检索 → 评估 → 引用", "agents/graph.py"),
        ],
    )
    layer(
        695,
        "检索与模型",
        [
            ("Dense + BM25", "RRF / BGE-Reranker", "retrieval/service.py"),
            ("GraphRAG / SQLRAG", "来源路径 / 受控只读查询", "storage/graph.py / retrieval/sql.py"),
            ("模型与解析客户端", "Qwen / BGE / 可选 MinerU", "clients/models.py / mineru.py"),
        ],
    )
    layer(
        890,
        "持久化与索引",
        [
            ("PostgreSQL · 15432", "权限、版本、任务、记录", "权威元数据"),
            ("Milvus · 19531", "Dense 与稀疏索引", "可重建投影"),
            ("Neo4j · 17687", "实体与来源关系", "可重建投影"),
            ("Redis · 16379", "Celery 队列与缓存", "身份范围参与缓存键"),
        ],
    )
    for y in [266, 461, 656, 851]:
        svg.append(f'<path d="M600 {y + 4} L600 {y + 27}" stroke="#315f84" stroke-width="5"/>')
        svg.append(f'<path d="M590 {y + 20} L600 {y + 34} L610 {y + 20}" fill="#315f84"/>')
    rect(30, 1090, 1140, 135, "#e8f1ed")
    text("横向能力：版本有效性 · 原文与引用 · 回归测试 · 检索评测 · 日志与可选 Langfuse", 600, 1125, 21, True)
    text("原始文件与解析产物保存在 data/；MinerU、Langfuse 和独立模型服务按配置接入。", 600, 1162, 18)
    text("本图展示职责分层；实际控制流与源码映射见 docs/01-architecture.md。", 600, 1195, 18)
    svg.append("</svg>")
    output = ROOT / "docs/images/architecture.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(svg), encoding="utf-8")
    print("Generated docs/images/architecture.svg")


if __name__ == "__main__":
    main()
