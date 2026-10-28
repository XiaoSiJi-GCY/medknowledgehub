import httpx
import pytest
from integrations.carepilot_client import MedKnowledgeHubClient, KnowledgeUnavailable


def test_source_metadata_and_verified_answer_contract():
    row = {
        "id": "chunk-1",
        "chunk_id": "chunk-1",
        "title": "资料",
        "url": "https://example.org/source",
        "summary": "资料原文",
        "version": 2,
        "score": 0.3,
        "citation_id": "S1",
    }

    def server(request):
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.method == "GET":
            return httpx.Response(200, json={"results": [row]})
        return httpx.Response(200, json={"answer": "有来源的回答 [S1]", "no_answer": False, "citations": [row]})

    client = MedKnowledgeHubClient("http://knowledge/api/v1", "test-token", transport=httpx.MockTransport(server))
    try:
        assert client.search("问题")[0]["version"] == 2
        assert client.answer("问题")["sources"][0]["citation_id"] == "S1"
    finally:
        client.close()


def test_invalid_citations_and_remote_errors_do_not_create_grounded_answers():
    client = MedKnowledgeHubClient(
        "http://knowledge/api/v1",
        "test-token",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"answer": "错误引用 [S9]", "no_answer": False, "citations": []})
        ),
    )
    try:
        assert client.answer("问题")["status"] == "no_evidence"
        with pytest.raises(ValueError):
            client.source("../private")
    finally:
        client.close()
    client = MedKnowledgeHubClient(
        "http://knowledge/api/v1",
        "test-token",
        transport=httpx.MockTransport(lambda request: httpx.Response(403, text="private server detail")),
    )
    try:
        with pytest.raises(KnowledgeUnavailable) as error:
            client.search("问题")
        assert "test-token" not in str(error.value) and "private server detail" not in str(error.value)
    finally:
        client.close()
