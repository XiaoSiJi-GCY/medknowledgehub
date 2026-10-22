import pytest

from app.core.errors import HubError
from app.schemas import QueryRequest
from app.services.answers import Answers
from tests.conftest import ingest


def test_cross_tenant_retrieval_and_source_are_denied(hub, owner, kb):
    ingest(hub, owner, kb)
    outsider = hub.identity.create_user("outsider", "password-123")
    with pytest.raises(HubError) as error:
        hub.kbs.scope(outsider, [kb.id])
    assert error.value.status == 403
    source_id = next(iter(hub.vectors.rows))
    with pytest.raises(HubError):
        hub.documents.source(outsider, source_id)
    assert hub.kbs.scope(outsider).version_ids == []


def test_revoke_invalidates_cached_results_and_stale_scope(hub, owner):
    private = hub.kbs.create(owner, {"name": "受限资料", "visibility": "restricted"})
    ingest(hub, owner, private)
    reader = hub.identity.create_user("reader", "password-123", owner.tenant_id, "viewer")
    hub.kbs.grant(owner, private.id, reader.id)
    scope = hub.kbs.scope(reader, [private.id])
    hits, _ = hub.retriever.search("咳嗽", scope)
    assert hits
    assert hub.retriever.search("咳嗽", scope)[1]["cache_hit"]
    hub.kbs.grant(owner, private.id, reader.id, revoke=True)
    with pytest.raises(HubError):
        hub.retriever.search("咳嗽", scope)


def test_untrusted_index_cannot_leak_other_tenant_chunks(hub, owner, kb):
    ingest(hub, owner, kb)
    other = hub.identity.create_user("another", "password-123")
    private = hub.kbs.create(other, {"name": "另一空间", "visibility": "tenant"})
    foreign = ingest(hub, other, private, "不应跨空间返回的资料正文。")
    foreign_ids = [key for key, row in hub.vectors.rows.items() if row["version_id"] == foreign["version_id"]]
    hub.vectors.leak_ids = foreign_ids
    hits, debug = hub.retriever.search("资料", hub.kbs.scope(owner))
    assert hits and not any(hit["id"] in foreign_ids for hit in hits)
    assert not set(debug["dense"]) & set(foreign_ids)
