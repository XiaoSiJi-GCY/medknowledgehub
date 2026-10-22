from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.core.errors import HubError
from app.models import Document, Grant, KnowledgeBase, User, Version
from app.services.identity import IdentityService, Principal


@dataclass
class Scope:
    principal: Principal
    kb_ids: list[str]
    version_ids: list[str]
    signature: str


class KnowledgeBases:
    def __init__(self, db):
        self.db = db

    def list(self, principal):
        with self.db.session() as session:
            rows = session.scalars(
                select(KnowledgeBase).where(
                    KnowledgeBase.tenant_id == principal.tenant_id, KnowledgeBase.archived.is_(False)
                )
            ).all()
            grants = set(session.scalars(select(Grant.kb_id).where(Grant.user_id == principal.id)).all())
            return [row for row in rows if principal.role == "admin" or row.visibility == "tenant" or row.id in grants]

    def require(self, principal, kb_id, write=False):
        if write:
            IdentityService.require_editor(principal)
        match = next((item for item in self.list(principal) if item.id == kb_id), None)
        if not match:
            raise HubError("知识库不存在或无权访问", 404)
        return match

    def create(self, principal, data):
        IdentityService.require_editor(principal)
        with self.db.session() as session:
            kb = KnowledgeBase(tenant_id=principal.tenant_id, **data)
            session.add(kb)
            session.flush()
            if kb.visibility == "restricted":
                session.add(Grant(kb_id=kb.id, user_id=principal.id))
            return kb

    def grant(self, principal, kb_id, user_id, revoke=False):
        IdentityService.require_admin(principal)
        self.require(principal, kb_id)
        with self.db.session() as session:
            user = session.get(User, user_id)
            if not user or user.tenant_id != principal.tenant_id:
                raise HubError("用户不存在", 404)
            grant = session.get(Grant, (kb_id, user_id))
            if revoke and grant:
                session.delete(grant)
            elif not revoke and not grant:
                session.add(Grant(kb_id=kb_id, user_id=user_id))
            session.get(KnowledgeBase, kb_id).epoch += 1

    def scope(self, principal, requested=None):
        requested = list(dict.fromkeys(requested or []))
        readable = self.list(principal)
        allowed = {kb.id for kb in readable}
        if set(requested) - allowed:
            raise HubError("请求包含无权访问的知识库", 403)
        ids = requested or sorted(allowed)
        with self.db.session() as session:
            versions = session.scalars(
                select(Version.id)
                .join(Document, Document.active_version_id == Version.id)
                .where(
                    Document.tenant_id == principal.tenant_id,
                    Document.kb_id.in_(ids),
                    Document.deleted.is_(False),
                    Version.status == "ready",
                    (Version.effective_on == "") | (Version.effective_on <= date.today().isoformat()),
                    (Version.expires_on == "") | (Version.expires_on >= date.today().isoformat()),
                )
            ).all()
        signature = "|".join(sorted(f"{kb.id}:{kb.epoch}" for kb in readable if kb.id in ids))
        return Scope(principal, ids, list(versions), signature)

    def archive(self, principal, kb_id):
        self.require(principal, kb_id, write=True)
        with self.db.session() as session:
            kb = session.get(KnowledgeBase, kb_id)
            kb.archived, kb.epoch = True, kb.epoch + 1
            for doc in session.scalars(select(Document).where(Document.kb_id == kb_id)).all():
                doc.deleted, doc.active_version_id = True, None
