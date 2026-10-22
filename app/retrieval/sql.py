"""Text-to-SQL over a scoped, allowlisted projection of business_records."""

import sqlglot
import json
from sqlglot import exp
from sqlalchemy import text

from app.core.errors import HubError

FIELDS = {"name", "category", "department", "value", "unit", "description", "chunk_id"}
FUNCTIONS = {"COUNT", "AVG", "SUM", "MIN", "MAX", "LOWER", "UPPER", "COALESCE", "CAST", "AND", "OR", "NOT"}


def compile_scoped_sql(sql, scope, dialect="postgres"):
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as exc:
        raise HubError("SQL 无法解析") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise HubError("仅允许一条 SELECT 查询")
    tree = statements[0]
    forbidden = {"Insert", "Update", "Delete", "Drop", "Create", "Command", "Into", "Lock", "Copy", "Attach", "With"}
    if any(node.__class__.__name__ in forbidden for node in tree.walk()):
        raise HubError("查询包含不允许的 SQL 结构")
    for function in tree.find_all(exp.Func):
        if function.sql_name() not in FUNCTIONS:
            raise HubError("查询使用了未开放的函数")
    aliases = {item.alias for item in tree.expressions if item.alias}
    if any(column.name not in FIELDS | aliases and column.name != "*" for column in tree.find_all(exp.Column)):
        raise HubError("查询包含未开放字段")
    tables = list(tree.find_all(exp.Table))
    if not tables or any(table.name != "records" or table.db or table.catalog for table in tables):
        raise HubError("仅允许查询 records 数据视图")
    literal = lambda value: exp.Literal.string(value)
    for table in tables:
        projection = (
            exp.select(*sorted(FIELDS))
            .from_("business_records")
            .where(
                exp.column("tenant_id").eq(literal(scope.principal.tenant_id)),
                exp.column("kb_id").isin(*[literal(item) for item in scope.kb_ids]),
                exp.column("version_id").isin(*[literal(item) for item in scope.version_ids]),
            )
        )
        table.replace(projection.subquery(table.alias_or_name))
    # Always bound the result even if an inner user-supplied LIMIT is larger.
    bounded = exp.select("*").from_(tree.subquery("scoped_result")).limit(50)
    return bounded.sql(dialect=dialect)


class SQLRetriever:
    def __init__(self, db, models, kbs=None):
        self.db, self.models, self.kbs = db, models, kbs

    def query(self, query, scope):
        if not scope.version_ids:
            return {"rows": [], "sql": "", "error": ""}
        error = ""
        for attempt in range(2):
            plan = self.models.json(
                "将用户的统计或结构化问题转为只读 SELECT。唯一可查询视图 records，字段 name、category、department、value、unit、description、chunk_id。"
                "value 是文本。禁止写操作、系统表、外部函数和 CTE。最多50行。中文条件使用 LIKE。返回 sql 和 explanation。",
                {"问题": query, "上次错误": error},
            )
            try:
                if self.kbs:
                    scope = self.kbs.scope(scope.principal, scope.kb_ids)
                dialect = "postgres" if self.db.engine.dialect.name == "postgresql" else "sqlite"
                sql = compile_scoped_sql(str(plan.get("sql", "")), scope, dialect)
                with self.db.engine.connect() as connection:
                    with connection.begin():
                        if dialect == "postgres":
                            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                            connection.exec_driver_sql("SET LOCAL statement_timeout = '3000ms'")
                        cursor = connection.execute(text(sql))
                        rows = [
                            json.loads(json.dumps(dict(row), default=str)) for row in cursor.mappings().fetchmany(50)
                        ]
                return {"rows": rows, "sql": plan["sql"], "error": ""}
            except Exception as exc:
                error = str(exc) if isinstance(exc, HubError) else "查询执行失败，请检查字段类型与 SQL 语法"
        return {"rows": [], "sql": "", "error": error}
