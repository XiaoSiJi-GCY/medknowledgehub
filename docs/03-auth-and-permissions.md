# 身份、知识空间与知识库权限

权限实现位于 `app/services/identity.py`、`app/services/knowledge_bases.py` 和 API 的 `principal()` 依赖。阅读时先区分用户、空间和知识库：用户属于一个空间，一个空间内可以有多个知识库；受限知识库还需要显式授权。

## 身份从哪里来

注册会创建独立空间的管理员；登录返回随机 Bearer token。密码采用随机盐与 PBKDF2-HMAC-SHA256 哈希，数据库只保存 token 摘要。普通登录 token 有 24 小时有效期，退出登录删除对应摘要。系统不采用客户端传入的 tenant_id、role 或自定义权限 Header。

初始化脚本另建 viewer 服务账号，将 `.env` 的 `SERVICE_TOKEN` 摘要绑定到这个账号。该 token 供 CarePilot/MCP 调用，不能创建或修改知识库；它是持久凭据，需保存在本机环境配置并按需要轮换。

## 角色与可见范围

| 角色 | 能力 |
| --- | --- |
| admin | 管理本空间成员，访问本空间知识库，授予或撤销访问 |
| editor | 修改自己可访问的知识库、资料和任务 |
| viewer | 读取自己可访问的知识库和证据 |

`tenant` 知识库对空间成员可读；`restricted` 知识库由 Grant 显式授权，管理员始终可访问本空间内的库。创建受限知识库的成员会获得访问权。角色不是跨空间的超级权限。

## 检索范围怎样形成

`KnowledgeBases.scope()` 生成 `Scope`：可信 Principal、可读 kb_ids、当前版本 version_ids 与 epoch 签名。显式请求无权访问的 kb_id 会返回 403；自动路由只看到当前可读知识库的说明。

范围同时进入 Milvus metadata filter、Neo4j 节点和关系过滤、SQL 权限子查询。候选 Chunk 回到 PostgreSQL 时再次校验空间、知识库、删除标记和当前版本。缓存键包含用户与范围签名，缓存命中也会重新确认权限。

## 学习实验

用管理员创建一个 viewer，将资料放入受限库。分别测试未授权检索、授权后读取、缓存命中、撤权后再次读取。然后用另一个注册账号请求同一原文和任务，确认得到拒绝响应。对应测试在 `tests/test_permissions.py`、`tests/test_api.py`。

## 当前边界

本项目没有接入企业 SSO、密码找回、强制多因素认证、登录限流和数据库静态加密。HTTP 与 MCP 的服务身份也不等于组织级授权平台。实际公开部署前应结合部署环境补充账号治理；学习时先把每次资源访问的服务端校验读清楚。
