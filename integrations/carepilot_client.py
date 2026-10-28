"""HTTP boundary to the knowledge service. Patient credentials never leave CarePilot."""

import re
import httpx


class KnowledgeUnavailable(RuntimeError):
    pass


class MedKnowledgeHubClient:
    backend = "medknowledgehub"

    def __init__(self, base_url, token, timeout=120, min_score=0.12, transport=None):
        if not token:
            raise ValueError("Knowledge service token is required")
        self.min_score = min_score
        self.client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + token},
            timeout=httpx.Timeout(timeout, connect=5),
            follow_redirects=False,
            transport=transport,
        )

    def _request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise KnowledgeUnavailable("知识服务暂不可用，请检查服务状态或接入凭据。") from None

    @staticmethod
    def _card(row):
        return {
            key: row[key]
            for key in (
                "id",
                "title",
                "url",
                "summary",
                "score",
                "citation_id",
                "chunk_id",
                "document_id",
                "version_id",
                "version",
                "kb_id",
                "section",
                "page",
                "publisher",
                "source_url",
            )
            if key in row
        }

    def search(self, query: str, limit: int = 2, min_score: float | None = None):
        query = query.strip()[:2000]
        if not query:
            return []
        result = self._request("GET", "knowledge/search", params={"q": query, "limit": limit})
        threshold = self.min_score if min_score is None else min_score
        return [self._card(row) for row in result["results"] if row["score"] >= threshold]

    def answer(self, query: str):
        result = self._request(
            "POST",
            "answers",
            json={
                "query": query.strip()[:2000],
                "mode": "hybrid",
                "enhance": False,
                "limit": 4,
            },
        )
        citations = result.get("citations", [])
        text = result.get("answer", "").strip()
        ids = {row.get("citation_id") for row in citations}
        refs = set(re.findall(r"\[(S\d+)\]", text))
        if result.get("no_answer", True) or not text or not citations or not refs or not refs <= ids:
            return {
                "answer": "当前知识库没有足够证据回答这个问题。可以补充具体问题，或在就诊时向医生确认。",
                "sources": [],
                "status": "no_evidence",
            }
        return {"answer": text, "sources": [self._card(row) for row in citations], "status": "answered"}

    def source(self, chunk_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", chunk_id):
            raise ValueError("资料编号格式不正确")
        return self._request("GET", "sources/" + chunk_id)

    def status(self):
        self._request("GET", "auth/me")
        result = self._request("GET", "knowledge-bases")
        return {"backend": self.backend, "status": "ready", "knowledge_bases": len(result["knowledge_bases"])}

    def close(self):
        self.client.close()
