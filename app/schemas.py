from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[\w.@-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserCreate(Credentials):
    role: Literal["editor", "viewer"] = "viewer"


class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    category: Literal["general", "disease", "guideline", "drug", "lab", "hospital"] = "general"
    visibility: Literal["tenant", "restricted"] = "tenant"


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    kb_ids: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=5, ge=1, le=20)
    mode: Literal["auto", "hybrid", "graph", "sql"] = "auto"
    enhance: bool = True
    history: list[ChatTurn] = Field(default_factory=list, max_length=8)

    @field_validator("query")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()


class FeedbackRequest(BaseModel):
    query_id: str
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class GrantRequest(BaseModel):
    user_id: str


class QueryPlan(BaseModel):
    route: Literal["hybrid", "graph", "sql"] = "hybrid"
    kb_ids: list[str] = Field(default_factory=list, max_length=20)
    queries: list[str] = Field(default_factory=list, max_length=3)
    entities: list[str] = Field(default_factory=list, max_length=6)
    strategy: Literal["original", "rewrite", "hyde", "decompose"] = "original"
