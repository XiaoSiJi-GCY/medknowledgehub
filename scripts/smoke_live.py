"""Real HTTP + Celery + PostgreSQL/Milvus/Neo4j/Redis + model regression."""

import json
import secrets
import time
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import ROOT, get_settings


def main():
    settings = get_settings()
    suffix = uuid4().hex[:10]
    report = {"checks": {}, "kind": "live HTTP, real infrastructure and model APIs"}
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=240) as client:

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        assert call("GET", "/health/ready")["status"] == "ready"
        registration = call(
            "POST",
            "/api/v1/auth/register",
            json={"username": "regression-" + suffix, "password": secrets.token_urlsafe(16)},
        )
        token = registration["access_token"]
        client.headers["Authorization"] = "Bearer " + token
        kb = call("POST", "/api/v1/knowledge-bases", json={"name": "工程回归资料 " + suffix})

        def upload(text, document_id=None):
            data = {"kb_id": kb["id"], "title": "索引版本回归资料", "document_id": document_id or ""}
            result = call(
                "POST",
                "/api/v1/documents",
                data=data,
                files={"file": ("regression.md", text.encode(), "text/markdown")},
            )
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                task = call("GET", "/api/v1/tasks/" + result["task_id"])
                if task["status"] in {"succeeded", "failed"}:
                    assert task["status"] == "succeeded", task["error"]
                    return result
                time.sleep(1)
            raise TimeoutError("入库队列未完成，请确认 Worker 正在运行")

        first = upload("# 检索工程\n\n证据定位依赖文档版本。索引发布前必须保存原文位置。旧版标记：OLD-EVIDENCE。")[
            "document_id"
        ]
        result = call("POST", "/api/v1/retrieval/search", json={"query": "证据定位文档版本", "kb_ids": [kb["id"]]})
        assert result["results"]
        chunk_id = result["results"][0]["id"]
        assert call("GET", "/api/v1/sources/" + chunk_id)["version"] == 1
        report["checks"]["celery_ingestion_and_hybrid_search"] = "passed"
        replacement = upload(
            "# 检索工程\n\n证据定位依赖文档版本。新版本发布后只检索当前版本。新版标记：NEW-EVIDENCE。", first
        )
        result = call("POST", "/api/v1/retrieval/search", json={"query": "证据定位", "kb_ids": [kb["id"]]})
        assert result["results"] and all(row["version_id"] == replacement["version_id"] for row in result["results"])
        report["checks"]["version_switch"] = "passed"
        outsider = call(
            "POST",
            "/api/v1/auth/register",
            json={"username": "outsider-" + suffix, "password": secrets.token_urlsafe(16)},
        )
        response = client.get(
            "/api/v1/sources/" + chunk_id, headers={"Authorization": "Bearer " + outsider["access_token"]}
        )
        assert response.status_code == 404
        response = client.post(
            "/api/v1/retrieval/search",
            json={"query": "证据", "kb_ids": [kb["id"]]},
            headers={"Authorization": "Bearer " + outsider["access_token"]},
        )
        assert response.status_code == 403
        report["checks"]["cross_tenant_access"] = "passed"
        call("DELETE", "/api/v1/documents/" + first)
        assert call("POST", "/api/v1/retrieval/search", json={"query": "证据", "kb_ids": [kb["id"]]})["results"] == []
        call("DELETE", "/api/v1/knowledge-bases/" + kb["id"])
        report["checks"]["delete_and_archive"] = "passed"
        client.headers["Authorization"] = "Bearer " + settings.service_token.get_secret_value()
        for mode, question in [
            ("hybrid", "带状疱疹涉及眼部时需要注意什么？"),
            ("graph", "带状疱疹与皮疹、水疱是什么关系？"),
            ("sql", "结构化科室目录一共有多少个科室？"),
        ]:
            result = call("POST", "/api/v1/answers", json={"query": question, "mode": mode, "enhance": False})
            assert result["route"] == mode and not result["no_answer"], result["warnings"]
            if mode == "sql":
                assert next(iter(result["sql_rows"][0].values())) == 6
                assert "6" in result["answer"]
            else:
                assert result["citations"]
            report["checks"][mode + "_answer"] = "passed"
        compatibility = call("GET", "/api/v1/knowledge/search", params={"q": "咳嗽超过三周", "limit": 2})
        assert compatibility["results"] and {"id", "title", "url", "summary", "score"} <= set(
            compatibility["results"][0]
        )
        report["checks"]["carepilot_contract"] = "passed"
        response = client.post("/api/v1/answers/stream", json={"query": "咳嗽超过三周", "enhance": False})
        response.raise_for_status()
        assert "event: stage" in response.text and "event: done" in response.text
        report["checks"]["sse"] = "passed"
    output = ROOT / "artifacts/smoke-live.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
