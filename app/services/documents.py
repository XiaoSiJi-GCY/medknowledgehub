import difflib
import hashlib
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app.core.errors import HubError
from app.ingestion.parsers import validate_file
from app.models import Chunk, Document, IngestionTask, KnowledgeBase, Version
from app.storage.files import resolve_raw


class Documents:
    def __init__(self, db, kbs, settings):
        self.db, self.kbs, self.settings = db, kbs, settings

    def upload(self, principal, kb_id, filename, content, metadata, document_id=None, force=False):
        self.kbs.require(principal, kb_id, write=True)
        filename = filename.replace("\\", "/").split("/")[-1][:200]
        suffix = validate_file(filename, content, self.settings.max_upload_bytes)
        for key in ("published_on", "effective_on", "expires_on"):
            if metadata.get(key):
                try:
                    date.fromisoformat(metadata[key])
                except ValueError as exc:
                    raise HubError(f"{key} 需要 YYYY-MM-DD 日期") from exc
        url = metadata.get("source_url", "")
        if url and not url.startswith(("https://", "http://")):
            raise HubError("来源 URL 仅支持 http/https")
        normalized_metadata = {
            key: metadata.get(key, "")
            for key in ("source_url", "publisher", "published_on", "effective_on", "expires_on")
        }
        normalized_metadata["authority"] = metadata.get("authority", 0)
        fingerprint = hashlib.sha256(content + json.dumps(normalized_metadata, sort_keys=True).encode()).hexdigest()
        with self.db.session() as session:
            if document_id:
                doc = session.scalar(
                    select(Document)
                    .where(
                        Document.id == document_id,
                        Document.tenant_id == principal.tenant_id,
                        Document.kb_id == kb_id,
                        Document.deleted.is_(False),
                    )
                    .with_for_update()
                )
                if not doc:
                    raise HubError("文档不存在", 404)
                same = session.scalar(
                    select(Version).where(
                        Version.document_id == doc.id,
                        Version.fingerprint == fingerprint,
                        Version.status.in_(["queued", "processing", "ready"]),
                    )
                )
                if same and not force:
                    task = session.scalar(select(IngestionTask).where(IngestionTask.version_id == same.id))
                    return {"document_id": doc.id, "version_id": same.id, "task_id": task.id, "deduplicated": True}
            else:
                doc = Document(tenant_id=principal.tenant_id, kb_id=kb_id, title=metadata.pop("title", "") or filename)
                session.add(doc)
                session.flush()
            number = (session.scalar(select(func.max(Version.number)).where(Version.document_id == doc.id)) or 0) + 1
            version = Version(
                document_id=doc.id,
                number=number,
                fingerprint=fingerprint,
                filename=filename,
                raw_path="",
                **{
                    key: value
                    for key, value in metadata.items()
                    if key in {"source_url", "publisher", "published_on", "effective_on", "expires_on", "authority"}
                },
            )
            session.add(version)
            session.flush()
            folder = self.settings.data_path / "raw" / principal.tenant_id
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (version.id + suffix)
            path.write_bytes(content)
            version.raw_path = path.relative_to(self.settings.data_path).as_posix()
            task = IngestionTask(tenant_id=principal.tenant_id, kb_id=kb_id, version_id=version.id)
            session.add(task)
            session.flush()
            return {"document_id": doc.id, "version_id": version.id, "task_id": task.id, "deduplicated": False}

    def get(self, principal, document_id, write=False):
        with self.db.session() as session:
            doc = session.get(Document, document_id)
            if not doc or doc.deleted or doc.tenant_id != principal.tenant_id:
                raise HubError("文档不存在", 404)
            self.kbs.require(principal, doc.kb_id, write=write)
            return doc

    def list(self, principal, kb_id):
        self.kbs.require(principal, kb_id)
        with self.db.session() as session:
            return session.scalars(
                select(Document).where(
                    Document.kb_id == kb_id, Document.deleted.is_(False), Document.tenant_id == principal.tenant_id
                )
            ).all()

    def versions(self, principal, document_id):
        self.get(principal, document_id)
        with self.db.session() as session:
            return session.scalars(
                select(Version).where(Version.document_id == document_id).order_by(Version.number.desc())
            ).all()

    def delete(self, principal, document_id):
        self.get(principal, document_id, write=True)
        with self.db.session() as session:
            doc = session.get(Document, document_id)
            doc.deleted, doc.active_version_id = True, None
            session.get(KnowledgeBase, doc.kb_id).epoch += 1

    def source(self, principal, chunk_id):
        with self.db.session() as session:
            chunk = session.get(Chunk, chunk_id)
            if not chunk or chunk.tenant_id != principal.tenant_id:
                raise HubError("原文不存在", 404)
            self.get(principal, chunk.document_id)
            version = session.get(Version, chunk.version_id)
            return {
                "chunk_id": chunk.id,
                "text": chunk.text,
                "parent_text": chunk.parent_text,
                "page": chunk.page,
                "bbox": chunk.bbox,
                "section": chunk.section,
                "version": version.number,
                "source_url": version.source_url,
            }

    def compare(self, principal, document_id, old_id, new_id):
        self.get(principal, document_id)
        with self.db.session() as session:
            versions = session.scalars(
                select(Version).where(Version.document_id == document_id, Version.id.in_([old_id, new_id]))
            ).all()
            if len({v.id for v in versions}) != (1 if old_id == new_id else 2):
                raise HubError("版本不存在", 404)

            def text(vid):
                return "\n".join(
                    session.scalars(select(Chunk.text).where(Chunk.version_id == vid).order_by(Chunk.position)).all()
                ).splitlines()

            return {"diff": "\n".join(difflib.unified_diff(text(old_id), text(new_id), fromfile=old_id, tofile=new_id))}

    def reindex(self, principal, document_id):
        doc = self.get(principal, document_id, write=True)
        if not doc.active_version_id:
            raise HubError("文档尚无可重建的当前版本，请先处理入库任务", 409)
        with self.db.session() as session:
            version = session.get(Version, doc.active_version_id)
        metadata = {
            key: getattr(version, key)
            for key in ("source_url", "publisher", "published_on", "effective_on", "expires_on", "authority")
        }
        metadata["title"] = doc.title
        return self.upload(
            principal,
            doc.kb_id,
            version.filename,
            resolve_raw(self.settings, version.raw_path).read_bytes(),
            metadata,
            document_id=doc.id,
            force=True,
        )
