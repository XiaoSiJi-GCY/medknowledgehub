import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.models import BusinessRecord, Chunk, Document, KnowledgeBase, Version
from app.retrieval.fusion import rrf


class Retriever:
    def __init__(self, runtime):
        self.runtime = runtime

    def hydrate(self, ids, scope, scores=None):
        scope = self.runtime.kbs.scope(scope.principal, scope.kb_ids)
        if not ids or not scope.version_ids:
            return []
        with self.runtime.db.session() as session:
            rows = session.execute(
                select(Chunk, Document, Version)
                .join(Document, Chunk.document_id == Document.id)
                .join(Version, Chunk.version_id == Version.id)
                .where(
                    Chunk.id.in_(ids),
                    Chunk.tenant_id == scope.principal.tenant_id,
                    Chunk.kb_id.in_(scope.kb_ids),
                    Chunk.version_id.in_(scope.version_ids),
                    Document.deleted.is_(False),
                    Document.active_version_id == Chunk.version_id,
                )
            ).all()
            lookup = {}
            for chunk, document, version in rows:
                lookup[chunk.id] = {
                    "id": chunk.id,
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "version_id": version.id,
                    "version": version.number,
                    "kb_id": chunk.kb_id,
                    "title": document.title,
                    "url": version.source_url or f"http://127.0.0.1:8010/api/v1/sources/{chunk.id}",
                    "source_url": version.source_url,
                    "summary": chunk.text,
                    "text": chunk.text,
                    "section": chunk.section,
                    "page": chunk.page,
                    "bbox": chunk.bbox,
                    "parent_text": chunk.parent_text,
                    "position": chunk.position,
                    "publisher": version.publisher,
                    "published_on": version.published_on,
                    "authority": version.authority,
                    "score": (scores or {}).get(chunk.id, 0.0),
                }
        return [lookup[key] for key in dict.fromkeys(ids) if key in lookup]

    def search(self, query, scope, limit=5, queries=None, rerank=True):
        runtime = self.runtime
        if not scope.version_ids:
            return [], {"dense": [], "bm25": [], "cache_hit": False}
        key = (
            "retrieval:"
            + hashlib.sha256(
                json.dumps(
                    {
                        "user": scope.principal.id,
                        "scope": scope.signature,
                        "versions": sorted(scope.version_ids),
                        "query": query,
                        "queries": queries,
                        "limit": limit,
                        "rerank": rerank,
                        "models": [runtime.settings.embedding_model, runtime.settings.rerank_model],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
        )
        cached = runtime.cache.get(key)
        if cached:
            # Re-authorize using current authoritative metadata on every cache hit.
            fresh_scope = runtime.kbs.scope(scope.principal, scope.kb_ids)
            hits = self.hydrate(
                [item["id"] for item in cached["hits"]],
                fresh_scope,
                {item["id"]: item["score"] for item in cached["hits"]},
            )
            return hits[:limit], dict(cached["debug"], cache_hit=True)
        rankings, dense_ids, sparse_ids = [], [], []
        subqueries = list(dict.fromkeys(queries or [query]))[:3]
        vectors = runtime.models.embed(subqueries)

        def recall(pair):
            subquery, vector = pair
            return runtime.vectors.search(subquery, vector, scope, limit=25)

        with ThreadPoolExecutor(max_workers=min(len(subqueries), 3)) as pool:
            recalled = list(pool.map(recall, zip(subqueries, vectors)))
        for dense, sparse in recalled:
            rankings.extend([dense, sparse])
            dense_ids.extend(dense)
            sparse_ids.extend(sparse)
        candidates = self.hydrate(rrf(rankings)[:30], scope)
        if rerank and candidates:
            ordered = runtime.models.rerank(query, [item["text"] for item in candidates])
            hits = [dict(candidates[index], score=score) for index, score in ordered]
        else:
            hits = [dict(item, score=1 / (rank + 1)) for rank, item in enumerate(candidates)]
        authorized = {hit["id"] for hit in candidates}
        debug = {
            "dense": [key for key in dict.fromkeys(dense_ids) if key in authorized],
            "bm25": [key for key in dict.fromkeys(sparse_ids) if key in authorized],
            "cache_hit": False,
        }
        runtime.cache.set(key, {"hits": hits[:limit], "debug": debug})
        return hits[:limit], debug

    def graph(self, query, entities, scope):
        paths = self.runtime.graph_index.search(query, entities, scope)
        hits = self.hydrate([row["chunk_id"] for row in paths], scope, {row["chunk_id"]: 1.0 for row in paths})
        for hit in hits:
            hit["graph_paths"] = [row["path"] for row in paths if row["chunk_id"] == hit["id"]]
        return hits, [path for path in paths if path["chunk_id"] in {hit["id"] for hit in hits}]

    def sql_sources(self, scope):
        with self.runtime.db.session() as session:
            ids = session.scalars(
                select(BusinessRecord.chunk_id)
                .where(
                    BusinessRecord.tenant_id == scope.principal.tenant_id,
                    BusinessRecord.kb_id.in_(scope.kb_ids),
                    BusinessRecord.version_id.in_(scope.version_ids),
                )
                .limit(20)
            ).all()
        return self.hydrate(ids, scope, {key: 1.0 for key in ids})
