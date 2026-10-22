"""A per-process read-only service identity; no caller-supplied tenant/role is trusted."""

import os
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from app.core.config import get_settings
from app.schemas import QueryRequest

_context = {}


@asynccontextmanager
async def lifespan(server):
    from app.runtime import Runtime

    runtime = Runtime()
    settings = get_settings()
    token = os.getenv("MEDHUB_MCP_TOKEN") or settings.service_token.get_secret_value()
    user = runtime.identity.resolve(token)
    try:
        _context.update(runtime=runtime, principal=user)
        yield {"runtime": runtime, "principal": user}
    finally:
        _context.clear()
        runtime.close()


mcp = MCPServer("MedKnowledgeHub", lifespan=lifespan)


def context():
    if not _context:
        raise RuntimeError("MCP service context is not initialized")
    return _context


@mcp.tool()
def list_knowledge_bases() -> dict:
    """List knowledge bases visible to this process's service identity."""
    state = context()
    return {
        "knowledge_bases": [
            {"id": kb.id, "name": kb.name, "category": kb.category}
            for kb in state["runtime"].kbs.list(state["principal"])
        ]
    }


@mcp.tool()
def search_knowledge(query: str, kb_ids: list[str] | None = None, limit: int = 5) -> dict:
    """Hybrid retrieval with document version, location and source metadata."""
    request = QueryRequest(query=query, kb_ids=kb_ids or [], limit=limit)
    state = context()
    runtime = state["runtime"]
    scope = runtime.kbs.scope(state["principal"], request.kb_ids)
    hits, debug = runtime.retriever.search(query, scope, request.limit)
    return {"results": [{k: v for k, v in hit.items() if k != "parent_text"} for hit in hits]}


@mcp.tool()
def read_source(chunk_id: str) -> dict:
    """Read the original context of an authorized chunk."""
    state = context()
    return state["runtime"].documents.source(state["principal"], chunk_id)


@mcp.tool()
def query_relations(query: str, kb_ids: list[str] | None = None) -> dict:
    """Retrieve bounded source-backed relation paths."""
    state = context()
    runtime = state["runtime"]
    scope = runtime.kbs.scope(state["principal"], kb_ids or [])
    hits, paths = runtime.retriever.graph(QueryRequest(query=query).query, [], scope)
    return {"results": hits, "paths": paths}


@mcp.tool()
def query_structured(query: str, kb_ids: list[str] | None = None) -> dict:
    """Execute an allowlisted read-only query on authorized structured records."""
    state = context()
    runtime = state["runtime"]
    return runtime.sql.query(QueryRequest(query=query).query, runtime.kbs.scope(state["principal"], kb_ids or []))


@mcp.tool()
def compare_document_versions(document_id: str, old_id: str, new_id: str) -> dict:
    """Show a text diff between authorized versions of the same document."""
    state = context()
    return state["runtime"].documents.compare(state["principal"], document_id, old_id, new_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
