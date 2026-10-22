import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select, update

from app.core.errors import HubError
from app.ingestion.chunking import chunk_blocks
from app.ingestion.parsers import parse
from app.models import BusinessRecord, Chunk, Document, IngestionTask, KnowledgeBase, Version, now
from app.storage.files import resolve_raw


class IngestionPipeline:
    def __init__(self, runtime):
        self.runtime = runtime

    def progress(self, task_id, stage):
        with self.runtime.db.session() as session:
            task = session.get(IngestionTask, task_id)
            task.stage, task.updated_at = stage, now()

    def run(self, task_id):
        runtime = self.runtime
        stale_before = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        with runtime.db.session() as session:
            claim = session.execute(
                update(IngestionTask)
                .where(
                    IngestionTask.id == task_id,
                    (IngestionTask.status.in_(["queued", "failed"]))
                    | ((IngestionTask.status == "processing") & (IngestionTask.updated_at < stale_before)),
                )
                .values(
                    status="processing",
                    stage="parsing",
                    attempts=IngestionTask.attempts + 1,
                    error="",
                    updated_at=now(),
                )
            )
            if not claim.rowcount:
                return
            task = session.get(IngestionTask, task_id)
            version = session.get(Version, task.version_id)
            doc = session.get(Document, version.document_id)
            if doc.deleted:
                task.status, task.stage = "cancelled", "deleted"
                return
            version.status = "processing"
            context = {"tenant_id": doc.tenant_id, "kb_id": doc.kb_id, "document_id": doc.id, "version_id": version.id}
            path = resolve_raw(runtime.settings, version.raw_path)
        try:
            blocks, parser = parse(path, runtime.mineru)
            if sum(len(item["text"]) for item in blocks) > 300000:
                raise HubError("正文超过 30 万字符，请拆分文档后入库")
            self.progress(task_id, "chunking")
            chunks = chunk_blocks(blocks, context["version_id"])
            if not chunks:
                raise HubError("文档中没有可索引的正文")
            with runtime.db.session() as session:
                session.execute(delete(BusinessRecord).where(BusinessRecord.version_id == context["version_id"]))
                session.execute(delete(Chunk).where(Chunk.version_id == context["version_id"]))
                for item in chunks:
                    values = {key: value for key, value in item.items() if key != "record"}
                    session.add(Chunk(**values, **context))
                    if item.get("record"):
                        session.add(BusinessRecord(**context | {"chunk_id": item["id"]}, **item["record"]))
                session.get(Version, context["version_id"]).parser = parser
            parsed = runtime.settings.data_path / "parsed"
            parsed.mkdir(parents=True, exist_ok=True)
            (parsed / (context["version_id"] + ".json")).write_text(
                json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.progress(task_id, "embedding")
            vectors = []
            for offset in range(0, len(chunks), 16):
                self.progress(task_id, "embedding")
                vectors.extend(runtime.models.embed([item["text"] for item in chunks[offset : offset + 16]]))
            self.progress(task_id, "vector_index")
            indexed = [dict(item, **context) for item in chunks]
            runtime.vectors.delete_version(context["version_id"])
            runtime.vectors.upsert(indexed, vectors)
            self.progress(task_id, "graph_index")
            runtime.graph_index.delete_version(context["version_id"])
            for item in indexed:
                self.progress(task_id, "graph_index")
                edges = runtime.models.extract_edges(item["text"])
                runtime.graph_index.upsert(item, edges)
            self.progress(task_id, "publish")
            old_id = None
            with runtime.db.session() as session:
                doc = session.scalar(select(Document).where(Document.id == context["document_id"]).with_for_update())
                version = session.get(Version, context["version_id"])
                active = session.get(Version, doc.active_version_id) if doc.active_version_id else None
                if doc.deleted or (active and active.number > version.number):
                    version.status = "superseded"
                    old_id = version.id
                else:
                    old_id = doc.active_version_id
                    if active:
                        active.status = "retired"
                    version.status, doc.active_version_id = "ready", version.id
                    session.get(KnowledgeBase, context["kb_id"]).epoch += 1
                task = session.get(IngestionTask, task_id)
                task.status, task.stage, task.updated_at = "succeeded", "complete", now()
            if old_id and old_id != context["version_id"]:
                try:
                    runtime.vectors.delete_version(old_id)
                    runtime.graph_index.delete_version(old_id)
                except Exception:
                    with runtime.db.session() as session:
                        session.get(IngestionTask, task_id).warnings = [
                            "旧索引清理待重试；检索已按当前版本排除旧内容。"
                        ]
        except Exception as exc:
            with runtime.db.session() as session:
                task = session.get(IngestionTask, task_id)
                task.status, task.updated_at = "failed", now()
                task.error = (
                    str(exc)
                    if isinstance(exc, HubError)
                    else f"{task.stage} 失败（{type(exc).__name__}），请检查依赖与服务日志。"
                )
                session.get(Version, context["version_id"]).status = "failed"
            raise
