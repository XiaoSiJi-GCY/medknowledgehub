import asyncio

from mcp import Client


def test_mcp_tools_share_authenticated_scope(hub, owner, kb, monkeypatch):
    from app import mcp_server
    import app.runtime

    token = hub.identity.login("owner", "password-123")
    monkeypatch.setenv("MEDHUB_MCP_TOKEN", token)
    monkeypatch.setattr(app.runtime, "Runtime", lambda: hub)

    async def run():
        async with Client(mcp_server.mcp) as client:
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} >= {
                "search_knowledge",
                "read_source",
                "query_relations",
                "query_structured",
            }
            result = await client.call_tool("list_knowledge_bases", {})
            assert not result.is_error
            assert kb.id in str(result.structured_content or result.content)

    asyncio.run(run())
