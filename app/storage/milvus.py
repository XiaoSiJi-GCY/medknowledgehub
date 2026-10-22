import json
from threading import RLock

from pymilvus import DataType, Function, FunctionType, MilvusClient
from app.core.errors import HubError


class VectorIndex:
    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self.lock = RLock()

    def connect(self):
        with self.lock:
            if self.client is None:
                self.client = MilvusClient(uri=self.settings.milvus_uri, timeout=20)
        return self.client

    def ensure(self):
        client = self.connect()
        name = self.settings.milvus_collection
        if client.has_collection(name):
            schema = client.describe_collection(name)
            dense = next((field for field in schema["fields"] if field["name"] == "dense"), {})
            if int(dense.get("params", {}).get("dim", 0)) != self.settings.embedding_dimension:
                raise HubError("Milvus 集合维度与配置不一致，请使用新集合并重建索引。", 409)
            return
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
        for key in ("tenant_id", "kb_id", "document_id", "version_id"):
            schema.add_field(key, DataType.VARCHAR, max_length=64)
        schema.add_field(
            "text", DataType.VARCHAR, max_length=24000, enable_analyzer=True, analyzer_params={"tokenizer": "jieba"}
        )
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self.settings.embedding_dimension)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(
            Function(
                name="text_bm25",
                function_type=FunctionType.BM25,
                input_field_names=["text"],
                output_field_names=["sparse"],
            )
        )
        indexes = client.prepare_index_params()
        indexes.add_index("dense", index_type="AUTOINDEX", metric_type="COSINE")
        indexes.add_index("sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        client.create_collection(name, schema=schema, index_params=indexes, consistency_level="Strong")

    def upsert(self, chunks, vectors):
        self.ensure()
        rows = [
            {key: item[key] for key in ("id", "tenant_id", "kb_id", "document_id", "version_id", "text")}
            | {"dense": vector}
            for item, vector in zip(chunks, vectors)
        ]
        for offset in range(0, len(rows), 100):
            self.connect().upsert(self.settings.milvus_collection, rows[offset : offset + 100])

    @staticmethod
    def scope_filter(scope):
        return (
            f"tenant_id == {json.dumps(scope.principal.tenant_id)} and "
            f"kb_id in {json.dumps(scope.kb_ids)} and version_id in {json.dumps(scope.version_ids)}"
        )

    def search(self, query, vector, scope, limit=25):
        if not scope.version_ids:
            return [], []
        client = self.connect()
        params = {
            "collection_name": self.settings.milvus_collection,
            "filter": self.scope_filter(scope),
            "limit": limit,
            "output_fields": ["id"],
        }
        dense = client.search(data=[vector], anns_field="dense", search_params={"metric_type": "COSINE"}, **params)
        sparse = client.search(data=[query], anns_field="sparse", search_params={"metric_type": "BM25"}, **params)
        return ([item["id"] for item in dense[0]], [item["id"] for item in sparse[0]])

    def delete_version(self, version_id):
        self.ensure()
        self.connect().delete(self.settings.milvus_collection, filter=f"version_id == {json.dumps(version_id)}")

    def close(self):
        if self.client:
            self.client.close()
