from typing import Any
from typing_extensions import TypedDict


class RAGState(TypedDict, total=False):
    query: str
    scope: Any
    requested_mode: str
    enhance: bool
    limit: int
    plan: dict
    route: str
    queries: list[str]
    hits: list[dict]
    debug: dict
    sql: dict
    attempts: int
    sufficient: bool
    citations: list[dict]
    claims: list[dict]
    answer: str
    warnings: list[str]
    conflicts: list[dict]
    initial_kb_ids: list[str]
    history: list[dict]
    structured_answer: bool
