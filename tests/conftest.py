import re

import pytest

from app.core.config import Settings
from app.models import Base
from app.runtime import Runtime
from app.storage.database import Database


class ControlledModels:
    def __init__(self):
        self.embeddings = 0
        self.bad_citations = False
        self.empty = False
        self.sql = "SELECT name, department FROM records ORDER BY name"

    def embed(self, texts):
        self.embeddings += len(texts)
        return [[1.0] * 8 for _ in texts]

    def rerank(self, query, documents):
        return [(index, 0.9 if not self.empty else 0.0) for index in range(len(documents))]

    def extract_edges(self, text):
        return []

    def json(self, prompt, payload):
        if "只读 SELECT" in prompt:
            return {"sql": self.sql}
        if "制定计划" in prompt:
            return {"route": "hybrid", "kb_ids": [], "queries": [payload["问题"]], "entities": []}
        if "第一次检索" in prompt:
            return {"queries": [payload["问题"]]}
        if "claims" in prompt:
            source = payload["证据"][0]
            return {
                "claims": [
                    {
                        "text": "依据资料整理的回答",
                        "source_ids": ["S999" if self.bad_citations else source["id"]],
                        "quotes": {source["id"]: source["text"][:20]},
                    }
                ]
            }
        raise AssertionError(prompt)


class ControlledVectors:
    def __init__(self):
        self.rows = {}
        self.calls = 0
        self.leak_ids = []

    def ensure(self):
        pass

    def upsert(self, chunks, vectors):
        self.rows.update({chunk["id"]: dict(chunk) for chunk in chunks})

    def delete_version(self, version_id):
        self.rows = {key: row for key, row in self.rows.items() if row["version_id"] != version_id}

    def search(self, query, vector, scope, limit=25):
        self.calls += 1
        ids = [
            key
            for key, row in self.rows.items()
            if row["tenant_id"] == scope.principal.tenant_id
            and row["kb_id"] in scope.kb_ids
            and row["version_id"] in scope.version_ids
        ]
        return ids[:limit] + self.leak_ids, ids[:limit] + self.leak_ids


class ControlledGraph:
    def __init__(self):
        self.paths = []

    def upsert(self, chunk, edges):
        pass

    def delete_version(self, version_id):
        pass

    def search(self, query, entities, scope):
        return self.paths


class ControlledCache:
    def __init__(self):
        self.rows = {}

    def get(self, key):
        return self.rows.get(key)

    def set(self, key, value, ttl=300):
        self.rows[key] = value


@pytest.fixture
def hub(tmp_path):
    db = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(db.engine)
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        data_dir=tmp_path,
        embedding_dimension=8,
        task_mode="inline",
        langfuse_enabled=False,
    )
    runtime = Runtime(
        settings,
        db=db,
        models=ControlledModels(),
        vectors=ControlledVectors(),
        graph_index=ControlledGraph(),
        cache=ControlledCache(),
    )
    yield runtime
    runtime.close()


@pytest.fixture
def owner(hub):
    return hub.identity.create_user("owner", "password-123")


@pytest.fixture
def kb(hub, owner):
    return hub.kbs.create(
        owner, {"name": "测试资料", "description": "测试", "category": "general", "visibility": "tenant"}
    )


def ingest(
    hub, owner, kb, text="咳嗽持续超过三周应向医生咨询。原文用于验证引用与状态。", document_id=None, filename="notes.md"
):
    result = hub.documents.upload(
        owner,
        kb.id,
        filename,
        text.encode(),
        {"title": "资料", "source_url": "https://example.org/source"},
        document_id,
    )
    hub.pipeline.run(result["task_id"])
    return result
