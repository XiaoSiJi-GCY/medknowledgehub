import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.routes import router
from app.core.errors import HubError


def create_app(runtime=None):
    @asynccontextmanager
    async def lifespan(app):
        if runtime is None:
            from app.runtime import Runtime

            app.state.runtime = Runtime()
        else:
            app.state.runtime = runtime
        yield
        if runtime is None:
            app.state.runtime.close()

    app = FastAPI(title="MedKnowledgeHub", version="1.0.0", lifespan=lifespan)
    if runtime is not None:
        app.state.runtime = runtime

    @app.exception_handler(HubError)
    async def known_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code})

    @app.exception_handler(Exception)
    async def unknown_error(request, exc):
        logging.getLogger("medhub.errors").error("request failed type=%s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "服务执行失败，请检查依赖状态与任务记录。"})

    @app.middleware("http")
    async def trace_request(request: Request, call_next):
        request_id, started = uuid4().hex, time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("medhub.http").info(
            "request_id=%s method=%s status=%s latency_ms=%.1f",
            request_id,
            request.method,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/health/ready")
    def ready(request: Request):
        r, states = request.app.state.runtime, {}

        def database():
            with r.db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))

        checks = {
            "postgres": database,
            "redis": lambda: r.cache.client.ping(),
            "neo4j": lambda: r.graph_index.driver.verify_connectivity(),
            "milvus": lambda: r.vectors.connect().list_collections(),
        }
        for name, check in checks.items():
            try:
                check()
                states[name] = "ready"
            except Exception:
                states[name] = "unavailable"
        ok = all(value == "ready" for value in states.values())
        return JSONResponse(
            status_code=200 if ok else 503, content={"status": "ready" if ok else "degraded", "services": states}
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(router)
    return app


app = create_app()
