import json

import pytest

from app.core.errors import HubError
from app.retrieval.sql import compile_scoped_sql
from tests.conftest import ingest


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM records",
        "SELECT * FROM users",
        "SELECT pg_sleep(10) FROM records",
        "SELECT * FROM records; DROP TABLE users",
        "SELECT password_hash FROM records",
        "SELECT * INTO copied FROM records",
        "SELECT * FROM public.records",
    ],
)
def test_sql_rejects_unsafe_queries(hub, owner, kb, sql):
    with pytest.raises(HubError):
        compile_scoped_sql(sql, hub.kbs.scope(owner))


def test_sql_actual_execution_is_scoped(hub, owner, kb):
    corpus = json.dumps(
        {"records": [{"name": "皮肤科", "category": "科室", "department": "皮肤科"}]}, ensure_ascii=False
    )
    ingest(hub, owner, kb, corpus, filename="records.json")
    other = hub.identity.create_user("foreign", "password-123")
    private = hub.kbs.create(other, {"name": "其他", "visibility": "tenant"})
    ingest(hub, other, private, corpus.replace("皮肤科", "神经科"), filename="records.json")
    result = hub.sql.query("有哪些科室", hub.kbs.scope(owner))
    assert result["rows"] == [{"name": "皮肤科", "department": "皮肤科"}]
    hub.models.sql = "SELECT COUNT(*) AS total FROM records"
    assert hub.sql.query("多少科室", hub.kbs.scope(owner))["rows"] == [{"total": 1}]
    hub.models.sql = "SELECT COUNT(*) AS total FROM records WHERE category='科室' OR name='皮肤科'"
    assert hub.sql.query("科室数量", hub.kbs.scope(owner))["rows"] == [{"total": 1}]
