import hashlib

from neo4j import GraphDatabase, Query


class GraphIndex:
    def __init__(self, settings):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            connection_timeout=10,
        )

    def ensure(self):
        self.driver.execute_query("CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.key IS UNIQUE")

    def upsert(self, chunk, edges):
        rows = []
        for edge in edges:
            key = lambda name: hashlib.sha256(f"{chunk['tenant_id']}:{chunk['kb_id']}:{name}".encode()).hexdigest()
            row = dict(
                edge,
                source_key=key(edge["source"]),
                target_key=key(edge["target"]),
                **{k: chunk[k] for k in ("tenant_id", "kb_id", "version_id", "document_id")},
                chunk_id=chunk["id"],
            )
            row["edge_key"] = hashlib.sha256(f"{chunk['id']}:{edge}".encode()).hexdigest()
            rows.append(row)
        if not rows:
            return
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (s:Entity {key: row.source_key})
            SET s.name=row.source, s.tenant_id=row.tenant_id, s.kb_id=row.kb_id
            MERGE (t:Entity {key: row.target_key})
            SET t.name=row.target, t.tenant_id=row.tenant_id, t.kb_id=row.kb_id
            MERGE (s)-[r:REL {key: row.edge_key}]->(t)
            SET r += {kind:row.relation, quote:row.quote, tenant_id:row.tenant_id, kb_id:row.kb_id,
                      chunk_id:row.chunk_id, document_id:row.document_id, version_id:row.version_id}
        """,
            rows=rows,
        )

    def search(self, query, entities, scope):
        if not scope.version_ids:
            return []
        seeds = [str(item) for item in entities[:6] if str(item)] or [query[:100]]
        with self.driver.session() as session:
            result = session.run(
                Query(
                    """
                MATCH (start:Entity)
                WHERE start.tenant_id=$tenant AND start.kb_id IN $kbs
                  AND any(term IN $terms WHERE start.name CONTAINS term OR term CONTAINS start.name)
                MATCH path=(start)-[:REL*1..3]-(other:Entity)
                WHERE all(node IN nodes(path) WHERE node.tenant_id=$tenant AND node.kb_id IN $kbs)
                  AND all(edge IN relationships(path) WHERE edge.tenant_id=$tenant
                          AND edge.kb_id IN $kbs AND edge.version_id IN $versions)
                UNWIND relationships(path) AS edge
                RETURN DISTINCT edge.chunk_id AS chunk_id,
                    [n IN nodes(path) | n.name] AS path, edge.quote AS quote
                LIMIT 40
            """,
                    timeout=5,
                ),
                tenant=scope.principal.tenant_id,
                kbs=scope.kb_ids,
                versions=scope.version_ids,
                terms=seeds,
            )
            return [dict(record) for record in result]

    def delete_version(self, version_id):
        self.driver.execute_query("MATCH ()-[r:REL {version_id:$version}]->() DELETE r", version=version_id)

    def close(self):
        self.driver.close()
