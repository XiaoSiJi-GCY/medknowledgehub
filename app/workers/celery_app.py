from celery import Celery

from app.core.config import get_settings
from app.core.errors import HubError

settings = get_settings()
celery_app = Celery("medknowledgehub", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    task_default_queue="medhub-ingestion",
)


@celery_app.task(bind=True, name="medhub.ingest", max_retries=2)
def ingest_document(self, task_id):
    from app.runtime import worker_runtime

    try:
        worker_runtime().pipeline.run(task_id)
    except HubError:
        raise  # invalid document inputs require correction, not repeated model calls
    except Exception as exc:
        raise self.retry(exc=RuntimeError(type(exc).__name__), countdown=min(10 * (self.request.retries + 1), 30))


@celery_app.task(name="medhub.cleanup")
def cleanup_indexes():
    from sqlalchemy import select
    from app.models import Document, Version
    from app.runtime import worker_runtime

    runtime = worker_runtime()
    with runtime.db.session() as session:
        ids = session.scalars(
            select(Version.id)
            .join(Document, Version.document_id == Document.id)
            .where(Document.deleted.is_(True) | Version.status.in_(["retired", "superseded"]))
        ).all()
    for version_id in ids:
        runtime.vectors.delete_version(version_id)
        runtime.graph_index.delete_version(version_id)
    return {"cleaned_versions": len(ids)}
