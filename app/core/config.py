from functools import lru_cache
from pathlib import Path
import os
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
SUITE_ENV = Path(os.getenv("CARE_SUITE_ENV_FILE", ROOT.parent / "care-suite" / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", SUITE_ENV), env_file_encoding="utf-8", extra="ignore")
    database_url: SecretStr = SecretStr("sqlite+pysqlite:///:memory:")
    redis_url: str = "redis://127.0.0.1:16379/0"
    milvus_uri: str = "http://127.0.0.1:19531"
    milvus_collection: str = "medhub_chunks_v1"
    neo4j_uri: str = "bolt://127.0.0.1:17687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.siliconflow.cn/v1"
    openai_api_key: SecretStr = SecretStr("")
    model_name: str = "Qwen/Qwen3.5-9B"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_base_url: str = ""
    rerank_api_url: str = ""
    task_mode: Literal["celery", "inline"] = "celery"
    data_dir: Path = ROOT / "data"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_retrieval_attempts: int = 2
    context_chars: int = 12000
    context_token_budget: int = 6000
    min_relevance: float = 0.12
    mineru_api_url: str = ""
    mineru_api_key: SecretStr = SecretStr("")
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = "https://cloud.langfuse.com"
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    service_token: SecretStr = SecretStr("")

    @property
    def data_path(self):
        return self.data_dir if self.data_dir.is_absolute() else ROOT / self.data_dir


@lru_cache
def get_settings():
    return Settings()
