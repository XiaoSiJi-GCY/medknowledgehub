import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import inspect, select

from app.core.errors import HubError
from app.models import Feedback, Grant, IngestionTask, KnowledgeBase, QueryLog, User
from app.schemas import Credentials, FeedbackRequest, GrantRequest, KBCreate, QueryRequest, UserCreate
from app.services.answers import Answers
from app.services.identity import IdentityService

router = APIRouter(prefix="/api/v1")
bearer = HTTPBearer(auto_error=False)


def runtime(request: Request):
    return request.app.state.runtime


def principal(r=Depends(runtime), credential: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credential:
        raise HubError("请先登录", 401)
    return r.identity.resolve(credential.credentials)


def public(row):
    return {
        column.key: getattr(row, column.key)
        for column in inspect(type(row)).columns
        if column.key not in {"password_hash", "raw_path"}
    }


@router.post("/auth/register", tags=["auth"])
def register(payload: Credentials, r=Depends(runtime)):
    r.identity.create_user(payload.username, payload.password)
    return {"access_token": r.identity.login(payload.username, payload.password), "token_type": "bearer"}


@router.post("/auth/login", tags=["auth"])
def login(payload: Credentials, r=Depends(runtime)):
    return {"access_token": r.identity.login(payload.username, payload.password), "token_type": "bearer"}


@router.get("/auth/me", tags=["auth"])
def me(user=Depends(principal)):
    return user.__dict__


@router.post("/auth/logout", tags=["auth"])
def logout(r=Depends(runtime), user=Depends(principal), credential=Depends(bearer)):
    r.identity.logout(credential.credentials)
    return {"ok": True}


@router.post("/users", tags=["auth"])
def create_user(payload: UserCreate, r=Depends(runtime), user=Depends(principal)):
    IdentityService.require_admin(user)
    return r.identity.create_user(payload.username, payload.password, user.tenant_id, payload.role).__dict__


@router.get("/users", tags=["auth"])
def users(r=Depends(runtime), user=Depends(principal)):
    IdentityService.require_admin(user)
    with r.db.session() as session:
        return {
            "users": [
                public(row) for row in session.scalars(select(User).where(User.tenant_id == user.tenant_id)).all()
            ]
        }


@router.get("/knowledge-bases", tags=["knowledge-bases"])
def list_kbs(r=Depends(runtime), user=Depends(principal)):
    return {"knowledge_bases": [public(kb) for kb in r.kbs.list(user)]}


@router.post("/knowledge-bases", tags=["knowledge-bases"])
def create_kb(payload: KBCreate, r=Depends(runtime), user=Depends(principal)):
    return public(r.kbs.create(user, payload.model_dump()))


@router.put("/knowledge-bases/{kb_id}", tags=["knowledge-bases"])
def update_kb(kb_id: str, payload: KBCreate, r=Depends(runtime), user=Depends(principal)):
    r.kbs.require(user, kb_id, write=True)
    with r.db.session() as session:
        kb = session.get(KnowledgeBase, kb_id)
        for key, value in payload.model_dump().items():
            setattr(kb, key, value)
        if kb.visibility == "restricted" and not session.get(Grant, (kb_id, user.id)):
            session.add(Grant(kb_id=kb_id, user_id=user.id))
        kb.epoch += 1
        return public(kb)


@router.delete("/knowledge-bases/{kb_id}", tags=["knowledge-bases"])
def archive_kb(kb_id: str, r=Depends(runtime), user=Depends(principal)):
    r.kbs.archive(user, kb_id)
    return {"ok": True}


@router.post("/knowledge-bases/{kb_id}/grants", tags=["knowledge-bases"])
def grant(kb_id: str, payload: GrantRequest, r=Depends(runtime), user=Depends(principal)):
    r.kbs.grant(user, kb_id, payload.user_id)
    return {"ok": True}


@router.delete("/knowledge-bases/{kb_id}/grants/{user_id}", tags=["knowledge-bases"])
def revoke(kb_id: str, user_id: str, r=Depends(runtime), user=Depends(principal)):
    r.kbs.grant(user, kb_id, user_id, revoke=True)
    return {"ok": True}


@router.post("/documents", tags=["documents"])
async def upload(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    title: str = Form(""),
    document_id: str | None = Form(None),
    source_url: str = Form(""),
    publisher: str = Form(""),
    published_on: str = Form(""),
    effective_on: str = Form(""),
    expires_on: str = Form(""),
    authority: int = Form(0, ge=0, le=5),
    r=Depends(runtime),
    user=Depends(principal),
):
    content = await file.read(r.settings.max_upload_bytes + 1)
    result = r.documents.upload(
        user,
        kb_id,
        file.filename or "document.txt",
        content,
        {
            "title": title[:300],
            "source_url": source_url[:2000],
            "publisher": publisher[:200],
            "published_on": published_on,
            "effective_on": effective_on,
            "expires_on": expires_on,
            "authority": authority,
        },
        document_id,
    )
    try:
        r.dispatch(result["task_id"])
    except HubError:
        raise
    except Exception:
        result["dispatch_warning"] = "任务已保存；执行服务暂不可用，可在任务页重试。"
    return result


@router.get("/documents", tags=["documents"])
def documents(kb_id: str, r=Depends(runtime), user=Depends(principal)):
    return {"documents": [public(doc) for doc in r.documents.list(user, kb_id)]}


@router.get("/documents/{document_id}/versions", tags=["documents"])
def versions(document_id: str, r=Depends(runtime), user=Depends(principal)):
    return {"versions": [public(version) for version in r.documents.versions(user, document_id)]}


@router.get("/documents/{document_id}/compare", tags=["documents"])
def compare(document_id: str, old_id: str, new_id: str, r=Depends(runtime), user=Depends(principal)):
    return r.documents.compare(user, document_id, old_id, new_id)


@router.delete("/documents/{document_id}", tags=["documents"])
def delete_document(document_id: str, r=Depends(runtime), user=Depends(principal)):
    r.documents.delete(user, document_id)
    return {"ok": True}


@router.post("/documents/{document_id}/reindex", tags=["documents"])
def reindex(document_id: str, r=Depends(runtime), user=Depends(principal)):
    result = r.documents.reindex(user, document_id)
    r.dispatch(result["task_id"])
    return result


@router.get("/tasks", tags=["tasks"])
def tasks(kb_id: str, r=Depends(runtime), user=Depends(principal)):
    r.kbs.require(user, kb_id)
    with r.db.session() as session:
        rows = session.scalars(
            select(IngestionTask)
            .where(IngestionTask.tenant_id == user.tenant_id, IngestionTask.kb_id == kb_id)
            .order_by(IngestionTask.updated_at.desc())
            .limit(100)
        ).all()
        return {"tasks": [public(row) for row in rows]}


@router.get("/tasks/{task_id}", tags=["tasks"])
def task(task_id: str, r=Depends(runtime), user=Depends(principal)):
    with r.db.session() as session:
        row = session.get(IngestionTask, task_id)
        if not row or row.tenant_id != user.tenant_id:
            raise HubError("任务不存在", 404)
        r.kbs.require(user, row.kb_id)
        return public(row)


@router.post("/tasks/{task_id}/retry", tags=["tasks"])
def retry_task(task_id: str, r=Depends(runtime), user=Depends(principal)):
    row = task(task_id, r, user)
    r.kbs.require(user, row["kb_id"], write=True)
    stale = (
        row["status"] == "processing"
        and row["updated_at"] < (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    )
    if row["status"] not in {"queued", "failed"} and not stale:
        raise HubError("当前任务状态不能重试", 409)
    r.dispatch(task_id)
    return {"ok": True}


@router.get("/sources/{chunk_id}", tags=["sources"])
def source(chunk_id: str, r=Depends(runtime), user=Depends(principal)):
    return r.documents.source(user, chunk_id)


@router.post("/retrieval/search", tags=["retrieval"])
def retrieve(payload: QueryRequest, r=Depends(runtime), user=Depends(principal)):
    scope = r.kbs.scope(user, payload.kb_ids)
    sql_rows = []
    if payload.mode == "graph":
        hits, paths = r.retriever.graph(payload.query, [], scope)
        debug = {"paths": paths}
    elif payload.mode == "sql":
        result = r.sql.query(payload.query, scope)
        sql_rows = result["rows"]
        hits = r.retriever.sql_sources(scope) if sql_rows else []
        debug = {"sql": result["sql"], "error": result["error"]}
    else:
        hits, debug = r.retriever.search(payload.query, scope, payload.limit)
    return {
        "results": [
            {key: value for key, value in hit.items() if key != "parent_text"} for hit in hits[: payload.limit]
        ],
        "debug": debug,
        "sql_rows": sql_rows,
    }


@router.get("/knowledge/search", tags=["carepilot"])
def compatible_search(
    q: str = Query(min_length=1, max_length=2000),
    limit: int = Query(default=2, ge=1, le=20),
    r=Depends(runtime),
    user=Depends(principal),
):
    return retrieve(QueryRequest(query=q, limit=limit), r, user)


@router.post("/answers", tags=["answers"])
def answer(payload: QueryRequest, r=Depends(runtime), user=Depends(principal)):
    return Answers(r).run(user, payload)


@router.post("/answers/stream", tags=["answers"])
def stream(payload: QueryRequest, r=Depends(runtime), user=Depends(principal)):
    events = Answers(r).stream(user, payload)

    def generate():
        try:
            for event in events:
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception:
            yield 'event: error\ndata: {"message":"检索问答执行失败，请检查服务状态。"}\n\n'

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/queries", tags=["feedback"])
def queries(r=Depends(runtime), user=Depends(principal)):
    readable = {kb.id for kb in r.kbs.list(user)}
    with r.db.session() as session:
        output = []
        for row in session.scalars(
            select(QueryLog)
            .where(QueryLog.user_id == user.id, QueryLog.tenant_id == user.tenant_id)
            .order_by(QueryLog.created_at.desc())
            .limit(50)
        ).all():
            value = public(row)
            if any(citation.get("kb_id") not in readable for citation in row.result.get("citations", [])):
                value["result"] = {
                    "answer": "部分资料的访问权限已变更，请重新查询。",
                    "citations": [],
                    "no_answer": True,
                }
            output.append(value)
        return {"queries": output}


@router.post("/feedback", tags=["feedback"])
def feedback(payload: FeedbackRequest, r=Depends(runtime), user=Depends(principal)):
    with r.db.session() as session:
        query = session.get(QueryLog, payload.query_id)
        if not query or query.user_id != user.id or query.tenant_id != user.tenant_id:
            raise HubError("查询记录不存在", 404)
        row = Feedback(user_id=user.id, **payload.model_dump())
        session.add(row)
        session.flush()
        return {"id": row.id}
