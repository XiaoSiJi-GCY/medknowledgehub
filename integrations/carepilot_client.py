"""Drop-in search interface. Copy this adapter into CarePilot when integration is enabled."""

import httpx


class MedKnowledgeHubClient:
    def __init__(self, base_url, token, timeout=30):
        self.client = httpx.Client(
            base_url=base_url.rstrip("/") + "/", timeout=timeout, headers={"Authorization": "Bearer " + token}
        )

    def search(self, query: str, limit: int = 2, min_score: float = 0.12) -> list[dict]:
        response = self.client.get("knowledge/search", params={"q": query, "limit": limit})
        response.raise_for_status()
        rows = response.json()["results"]
        return [
            {key: row[key] for key in ("id", "title", "url", "summary", "score")}
            for row in rows
            if row["score"] >= min_score
        ]

    def close(self):
        self.client.close()
