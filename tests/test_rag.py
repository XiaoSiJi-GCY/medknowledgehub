from app.schemas import QueryRequest
from app.services.answers import Answers
from tests.conftest import ingest


def test_answer_has_verifiable_citation_and_stream_events(hub, owner, kb):
    ingest(hub, owner, kb)
    answer = Answers(hub).run(owner, QueryRequest(query="咳嗽多久需要就医"))
    assert not answer["no_answer"] and "[S1]" in answer["answer"]
    assert answer["citations"][0]["version"] == 1
    events = list(Answers(hub).stream(owner, QueryRequest(query="咳嗽多久需要就医")))
    assert events[-1]["event"] == "done"
    assert any(event["event"] == "stage" for event in events)
    assert "".join(e["data"]["text"] for e in events if e["event"] == "answer_delta") == events[-1]["data"]["answer"]


def test_bad_citation_is_removed_instead_of_displayed(hub, owner, kb):
    ingest(hub, owner, kb)
    hub.models.bad_citations = True
    result = Answers(hub).run(owner, QueryRequest(query="咳嗽"))
    assert result["no_answer"] and "S999" not in result["answer"]


def test_no_answer_retrieval_loop_is_bounded(hub, owner, kb):
    ingest(hub, owner, kb)
    hub.models.empty = True
    result = Answers(hub).run(owner, QueryRequest(query="未收录的具体问题"))
    assert result["no_answer"]
    assert result["attempts"] == hub.settings.max_retrieval_attempts


def test_graph_paths_retain_original_sources(hub, owner, kb):
    ingest(hub, owner, kb)
    chunk_id = next(iter(hub.vectors.rows))
    hub.graph_index.paths = [{"chunk_id": chunk_id, "path": ["实体A", "实体B"], "quote": "资料"}]
    result = Answers(hub).run(owner, QueryRequest(query="实体关系", mode="graph", enhance=False))
    assert result["route"] == "graph"
    assert result["debug"]["paths"][0]["chunk_id"] == result["citations"][0]["id"]
