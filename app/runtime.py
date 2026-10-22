from functools import lru_cache

from app.agents.graph import build_graph
from app.clients.mineru import MinerUClient
from app.clients.models import Models
from app.core.config import get_settings
from app.ingestion.pipeline import IngestionPipeline
from app.observability.tracing import Tracing
from app.retrieval.service import Retriever
from app.retrieval.sql import SQLRetriever
from app.services.documents import Documents
from app.services.identity import IdentityService
from app.services.knowledge_bases import KnowledgeBases
from app.storage.cache import Cache
from app.storage.database import Database
from app.storage.graph import GraphIndex
from app.storage.milvus import VectorIndex


class Runtime:
    def __init__(self, settings=None, *, db=None, models=None, vectors=None, graph_index=None, cache=None):
        self.settings = settings or get_settings()
        self.db = db or Database(self.settings.database_url.get_secret_value())
        self.identity = IdentityService(self.db)
        self.kbs = KnowledgeBases(self.db)
        self.documents = Documents(self.db, self.kbs, self.settings)
        self.models = models or Models(self.settings, self.db)
        self.vectors = vectors or VectorIndex(self.settings)
        self.graph_index = graph_index or GraphIndex(self.settings)
        self.cache = cache or Cache(self.settings.redis_url)
        self.tracing = Tracing(self.settings)
        self.models.tracing = self.tracing
        self.mineru = MinerUClient(self.settings) if self.settings.mineru_api_url else None
        self.retriever = Retriever(self)
        self.sql = SQLRetriever(self.db, self.models, self.kbs)
        self.pipeline = IngestionPipeline(self)
        self.rag = build_graph(self)

    def dispatch(self, task_id):
        if self.settings.task_mode == "inline":
            self.pipeline.run(task_id)
        else:
            from app.workers.celery_app import ingest_document

            ingest_document.delay(task_id)

    def close(self):
        for resource in (self.models, self.vectors, self.graph_index, self.cache, self.tracing, self.db):
            close = getattr(resource, "close", None)
            if close:
                close()


@lru_cache
def worker_runtime():
    return Runtime()
