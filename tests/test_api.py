from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ingest


def test_login_upload_retrieval_answer_feedback_and_tenant_boundary(hub, owner, kb):
    with TestClient(create_app(hub)) as client:
        login = client.post("/api/v1/auth/login", json={"username": "owner", "password": "password-123"})
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        uploaded = client.post(
            "/api/v1/documents",
            data={"kb_id": kb.id, "title": "上传资料"},
            files={"file": ("note.md", "咳嗽持续超过三周应咨询医生。".encode(), "text/markdown")},
            headers=headers,
        )
        assert uploaded.status_code == 200
        task_id = uploaded.json()["task_id"]
        assert client.get(f"/api/v1/tasks/{task_id}", headers=headers).json()["status"] == "succeeded"
        search = client.get("/api/v1/knowledge/search", params={"q": "咳嗽"}, headers=headers)
        assert search.json()["results"][0]["title"] == "上传资料"
        answer = client.post("/api/v1/answers", json={"query": "咳嗽多久就医"}, headers=headers)
        assert answer.status_code == 200
        result = answer.json()
        assert result["citations"] and not result["no_answer"]
        assert (
            client.post(
                "/api/v1/feedback", json={"query_id": result["query_id"], "rating": 5}, headers=headers
            ).status_code
            == 200
        )
        stranger = client.post("/api/v1/auth/register", json={"username": "stranger", "password": "password-123"})
        other_headers = {"Authorization": "Bearer " + stranger.json()["access_token"]}
        denied = client.post(
            "/api/v1/retrieval/search", json={"query": "咳嗽", "kb_ids": [kb.id]}, headers=other_headers
        )
        assert denied.status_code == 403
        chunk = result["citations"][0]["id"]
        assert client.get("/api/v1/sources/" + chunk, headers=other_headers).status_code == 404
        assert client.get("/api/v1/tasks/" + task_id, headers=other_headers).status_code == 404
        assert client.get("/api/v1/knowledge/search", params={"q": "咳嗽"}).status_code == 401
        stream = client.post("/api/v1/answers/stream", json={"query": "咳嗽"}, headers=headers)
        assert "event: stage" in stream.text and "event: done" in stream.text
        assert (
            "raw_path"
            not in client.get(f"/api/v1/documents/{uploaded.json()['document_id']}/versions", headers=headers).text
        )


def test_viewer_cannot_write_and_spoofed_headers_do_not_change_scope(hub, owner, kb):
    hub.identity.create_user("viewer", "password-123", owner.tenant_id, "viewer")
    ingest(hub, owner, kb)
    with TestClient(create_app(hub)) as client:
        token = hub.identity.login("viewer", "password-123")
        headers = {"Authorization": "Bearer " + token, "X-Role": "admin", "X-Tenant-ID": "other"}
        response = client.post("/api/v1/knowledge-bases", json={"name": "越权创建"}, headers=headers)
        assert response.status_code == 403
        assert client.get("/api/v1/auth/me", headers=headers).json()["tenant_id"] == owner.tenant_id
        assert client.post("/api/v1/answers", json={"query": "  "}, headers=headers).status_code == 422
