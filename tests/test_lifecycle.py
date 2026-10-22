import pytest
from sqlalchemy import select

from app.models import Document, IngestionTask, Version
from tests.conftest import ingest


def test_version_publish_and_delete_remove_old_content(hub, owner, kb):
    first = ingest(hub, owner, kb)
    scope = hub.kbs.scope(owner)
    assert hub.retriever.search("咳嗽", scope)[0]
    updated = ingest(hub, owner, kb, "更新后的资料：新的就诊提示需要结合具体情况。", first["document_id"])
    current = hub.kbs.scope(owner)
    assert current.version_ids == [updated["version_id"]]
    hits, _ = hub.retriever.search("资料", current)
    assert all(hit["version_id"] == updated["version_id"] for hit in hits)
    assert hub.documents.compare(owner, first["document_id"], first["version_id"], updated["version_id"])["diff"]
    hub.documents.delete(owner, first["document_id"])
    assert hub.retriever.search("资料", hub.kbs.scope(owner))[0] == []


def test_failed_replacement_keeps_previous_active_version(hub, owner, kb, monkeypatch):
    first = ingest(hub, owner, kb)
    replacement = hub.documents.upload(owner, kb.id, "notes.md", b"replacement text", {}, first["document_id"])
    monkeypatch.setattr(hub.models, "embed", lambda texts: (_ for _ in ()).throw(RuntimeError("temporary failure")))
    with pytest.raises(RuntimeError):
        hub.pipeline.run(replacement["task_id"])
    with hub.db.session() as session:
        assert session.get(Document, first["document_id"]).active_version_id == first["version_id"]
        assert session.get(IngestionTask, replacement["task_id"]).status == "failed"


def test_task_replay_and_identical_version_are_idempotent(hub, owner, kb):
    first = ingest(hub, owner, kb)
    count = hub.models.embeddings
    hub.pipeline.run(first["task_id"])
    assert hub.models.embeddings == count
    same = ingest(hub, owner, kb, document_id=first["document_id"])
    assert same["deduplicated"]
    assert same["version_id"] == first["version_id"]


def test_expired_document_is_not_retrievable(hub, owner, kb):
    first = ingest(hub, owner, kb)
    with hub.db.session() as session:
        session.get(Version, first["version_id"]).expires_on = "2000-01-01"
    assert hub.kbs.scope(owner).version_ids == []


def test_reindex_builds_new_version_before_switching(hub, owner, kb):
    first = ingest(hub, owner, kb)
    second = hub.documents.reindex(owner, first["document_id"])
    assert second["version_id"] != first["version_id"]
    assert hub.kbs.scope(owner).version_ids == [first["version_id"]]
    hub.pipeline.run(second["task_id"])
    assert hub.kbs.scope(owner).version_ids == [second["version_id"]]
