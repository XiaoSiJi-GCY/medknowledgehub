# SQLRAG：从问题到受控只读查询

实现集中在 `app/retrieval/sql.py`，结构化资料来自 JSON records，经入库写入 PostgreSQL 的 `business_records`。当前字段包括 name、category、department、value、unit、description、chunk_id；value 保留文本，不冒充可直接比较的临床数值。

## 查询的四道边界

1. 模型只获得 `records` 视图的字段说明，生成一条 SELECT。
2. SQLGlot 解析 AST，拒绝多语句、写操作、系统表、未开放字段、函数及 CTE。
3. 编译器把每个 records 表引用替换为服务端构造的子查询，强制限制 tenant_id、kb_id 和 version_id；客户端不能用 OR 条件绕开外层范围。
4. PostgreSQL 使用只读事务、3 秒 statement_timeout，外层最多返回 50 行。执行失败可以反馈语法/类型信息给模型修正一次。

```sql
-- 模型生成
SELECT COUNT(*) AS total FROM records;
-- 编译后的逻辑形态
SELECT * FROM (
  SELECT COUNT(*) AS total
  FROM (
    SELECT ... FROM business_records
    WHERE tenant_id = <服务端身份>
      AND kb_id IN <可读知识库>
      AND version_id IN <当前有效版本>
  ) AS records
) AS scoped_result LIMIT 50;
```

实际 SQL 通过 AST 生成，示意中的尖括号不是可执行参数。

## 为什么统计结果不再交给模型重写

数据库已经返回的行和聚合值由程序直接格式化，回答同时保留 source 片段、原查询与结果，便于复核。比如“目录有多少个科室”会显示计算出的数量，而不是仅重复列举科室名称。

## 验证

阅读 `tests/test_sql.py`，比较 DELETE、多语句、pg_sleep、系统表和越权列的拒绝结果；再看两个空间拥有不同记录时实际 SELECT 与 COUNT 的输出。真实 SQL 路径还在 `scripts.smoke_live` 中验证。

目前开放的是一张有来源的结构化记录视图，不是任意医院数据库。接入排班或业务系统时，需新增正式数据同步与 Schema，而不是直接授予模型对全部表的读取权。
