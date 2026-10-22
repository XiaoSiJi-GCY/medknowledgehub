import logging
import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

REQUESTS = Counter("medhub_queries_total", "Knowledge queries", ["route", "status"])
LATENCY = Histogram("medhub_query_seconds", "Query latency", ["route"])
TOKENS = Counter("medhub_model_tokens_total", "Model token usage", ["model", "direction"])


class Tracing:
    def __init__(self, settings):
        self.client = None
        if settings.langfuse_enabled:
            if not settings.langfuse_public_key or not settings.langfuse_secret_key.get_secret_value():
                raise ValueError("启用 Langfuse 前需要配置公钥与密钥")
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                host=settings.langfuse_base_url,
            )

    @contextmanager
    def span(self, name, **metadata):
        started = time.perf_counter()
        if self.client:
            with self.client.start_as_current_span(name=name, metadata=metadata) as span:
                yield span
        else:
            yield None
        logging.getLogger("medhub.trace").info("stage=%s latency_ms=%.1f", name, (time.perf_counter() - started) * 1000)

    def close(self):
        if self.client:
            self.client.flush()
            self.client.shutdown()

    @contextmanager
    def generation(self, model):
        if self.client:
            with self.client.start_as_current_generation(name="chat", model=model) as generation:
                yield generation
        else:
            yield None
