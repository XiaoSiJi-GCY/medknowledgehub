import time

from app.models import QueryLog
from app.observability.tracing import LATENCY, REQUESTS


class Answers:
    def __init__(self, runtime):
        self.runtime = runtime

    def initial(self, principal, request):
        return {
            "query": request.query,
            "scope": self.runtime.kbs.scope(principal, request.kb_ids),
            "requested_mode": request.mode,
            "enhance": request.enhance,
            "limit": request.limit,
            "history": [turn.model_dump() for turn in request.history],
        }

    def result(self, principal, query, state, started):
        route = state.get("route", "hybrid")
        citations = [
            {key: value for key, value in hit.items() if key not in {"context", "parent_text"}}
            for hit in state.get("citations", [])
        ]
        elapsed = (time.perf_counter() - started) * 1000
        result = {
            "answer": state.get("answer", "当前没有足够证据。"),
            "citations": citations,
            "route": route,
            "plan": state.get("plan", {}),
            "attempts": state.get("attempts", 0),
            "warnings": state.get("warnings", []),
            "conflicts": state.get("conflicts", []),
            "debug": state.get("debug", {}),
            "sql_rows": state.get("sql", {}).get("rows", []),
            "latency_ms": round(elapsed, 2),
            "no_answer": not bool(citations or state.get("structured_answer")),
        }
        with self.runtime.db.session() as session:
            row = QueryLog(
                tenant_id=principal.tenant_id,
                user_id=principal.id,
                query=query,
                route=route,
                result=result,
                latency_ms=elapsed,
            )
            session.add(row)
            session.flush()
            result["query_id"] = row.id
        LATENCY.labels(route).observe(elapsed / 1000)
        REQUESTS.labels(route, "no_answer" if result["no_answer"] else "answered").inc()
        return result

    def run(self, principal, request):
        started = time.perf_counter()
        with self.runtime.tracing.span("rag", tenant_id=principal.tenant_id):
            state = self.runtime.rag.invoke(self.initial(principal, request), {"recursion_limit": 30})
        return self.result(principal, request.query, state, started)

    def stream(self, principal, request):
        initial = self.initial(principal, request)

        def events():
            started, state = time.perf_counter(), dict(initial)
            for update in self.runtime.rag.stream(initial, {"recursion_limit": 30}, stream_mode="updates"):
                for node, delta in update.items():
                    if delta:
                        state.update(delta)
                    yield {"event": "stage", "data": {"node": node, "attempts": state.get("attempts", 0)}}
            result = self.result(principal, request.query, state, started)
            for offset in range(0, len(result["answer"]), 40):
                yield {"event": "answer_delta", "data": {"text": result["answer"][offset : offset + 40]}}
            yield {"event": "done", "data": result}

        return events()
