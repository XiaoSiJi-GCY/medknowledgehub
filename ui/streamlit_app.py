"""Knowledge management UI. All permissions and data access are enforced by the API."""

import json
import os

import httpx
import streamlit as st

BASE = os.getenv("MEDHUB_API_URL", "http://127.0.0.1:8010/api/v1").rstrip("/")
st.set_page_config(page_title="MedKnowledgeHub", page_icon="📚", layout="wide")
st.title("MedKnowledgeHub · 医疗知识中台")
st.caption("管理资料、追溯证据，为就诊助手提供统一知识服务。")


def call(method, path, **kwargs):
    headers = {"Authorization": "Bearer " + st.session_state.get("token", "")}
    try:
        response = httpx.request(method, BASE + path, headers=headers, timeout=kwargs.pop("timeout", 120), **kwargs)
    except httpx.HTTPError as exc:
        raise RuntimeError("无法连接知识服务，请检查 API 与基础设施是否启动。") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "请求失败")
        except ValueError:
            detail = "服务响应异常"
        raise RuntimeError(str(detail))
    return response.json()


def citations(result):
    for source in result.get("citations", []):
        title = f"[{source['citation_id']}] {source['title']} · v{source['version']}"
        if source.get("page"):
            title += f" · 第 {source['page']} 页"
        with st.expander(title):
            st.write(source.get("section", ""))
            st.write(source["text"])
            st.caption(
                f"来源机构：{source.get('publisher') or '未提供'}｜发布日期：{source.get('published_on') or '未提供'}"
            )
            if source.get("source_url", "").startswith(("https://", "http://")):
                st.link_button("访问资料来源", source["source_url"])
            if st.button("读取原文上下文", key=f"source_{result.get('query_id')}_{source['id']}"):
                try:
                    st.write(call("GET", "/sources/" + source["id"])["parent_text"])
                except RuntimeError as exc:
                    st.error(str(exc))


if not st.session_state.get("token"):
    st.info("初次使用请先运行初始化和资料导入命令。管理员账号配置位于项目本机 .env；注册会创建独立知识空间。")
    with st.form("login"):
        operation = st.radio("账号操作", ["登录", "注册独立空间"], horizontal=True)
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        if st.form_submit_button("继续", type="primary"):
            try:
                path = "/auth/login" if operation == "登录" else "/auth/register"
                result = call("POST", path, json={"username": username, "password": password})
                st.session_state.token = result["access_token"]
                st.session_state.messages = []
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))
    st.stop()

try:
    profile = call("GET", "/auth/me", timeout=10)
    kbs = call("GET", "/knowledge-bases", timeout=10)["knowledge_bases"]
except RuntimeError as exc:
    st.error(str(exc))
    if st.button("返回登录"):
        st.session_state.clear()
        st.rerun()
    st.stop()

with st.sidebar:
    st.write(f"**{profile['username']}** · {profile['role']}")
    if st.button("退出登录"):
        call("POST", "/auth/logout")
        st.session_state.clear()
        st.rerun()
    st.caption("知识空间内的文档与查询记录由服务端隔离。")
    selected = st.multiselect("检索知识库（留空为全部可访问）", kbs, format_func=lambda row: row["name"])
    mode = st.selectbox(
        "检索方式",
        ["auto", "hybrid", "graph", "sql"],
        format_func=lambda value: {
            "auto": "自动选择",
            "hybrid": "混合检索",
            "graph": "图关系检索",
            "sql": "结构化查询",
        }[value],
    )
    enhance = st.checkbox("按需改写与查询规划", value=True)
    limit = st.slider("返回证据数量", 1, 10, 5)

chat_tab, doc_tab, kb_tab, debug_tab = st.tabs(["知识问答", "资料与版本", "知识库与权限", "检索检查与反馈"])
with chat_tab:
    if not kbs:
        st.info("先创建知识库并上传资料，完成入库后即可问答。")
    for index, item in enumerate(st.session_state.get("messages", [])):
        with st.chat_message(item["role"]):
            st.write(item["content"])
            if item.get("result"):
                citations(item["result"])
                for warning in item["result"].get("warnings", []):
                    st.caption(warning)
    if prompt := st.chat_input("输入知识问题，例如：带状疱疹有哪些需要及时就医的情况？"):
        payload = {
            "query": prompt,
            "kb_ids": [row["id"] for row in selected],
            "mode": mode,
            "enhance": enhance,
            "limit": limit,
        }
        payload["history"] = [
            {"role": item["role"], "content": item["content"][:2000]}
            for item in st.session_state.get("messages", [])[-8:]
        ]
        st.session_state.setdefault("messages", []).append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        try:
            with st.chat_message("assistant"):
                status, answer_area = st.empty(), st.empty()
                status.caption("正在分析问题并检索资料…")
                answer, result, event_name = "", None, ""
                with httpx.stream(
                    "POST",
                    BASE + "/answers/stream",
                    json=payload,
                    headers={"Authorization": "Bearer " + st.session_state.token},
                    timeout=240,
                ) as response:
                    if response.status_code >= 400:
                        response.read()
                        raise RuntimeError(str(response.json().get("detail", "请求失败")))
                    for line in response.iter_lines():
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                        elif line.startswith("data:"):
                            data = json.loads(line[5:].strip())
                            if event_name == "stage":
                                status.caption("正在处理：" + data["node"])
                            elif event_name == "answer_delta":
                                answer += data["text"]
                                answer_area.write(answer)
                            elif event_name == "done":
                                result = data
                            elif event_name == "error":
                                raise RuntimeError(data["message"])
                status.empty()
                if result is None:
                    raise RuntimeError("连接结束，未收到完整回答；请重试。")
                st.session_state.last_result = result
                st.session_state.messages.append({"role": "assistant", "content": result["answer"], "result": result})
                st.rerun()
        except (RuntimeError, httpx.HTTPError, ValueError) as exc:
            st.error(str(exc) if isinstance(exc, RuntimeError) else "问答连接异常，请检查服务状态后重试。")

with doc_tab:
    if kbs:
        kb = st.selectbox("资料所属知识库", kbs, format_func=lambda row: row["name"], key="document_kb")
        documents = call("GET", "/documents", params={"kb_id": kb["id"]})["documents"]
        if profile["role"] in {"admin", "editor"}:
            with st.form("upload"):
                existing = st.selectbox(
                    "版本目标",
                    [None, *documents],
                    format_func=lambda row: "创建新文档" if row is None else row["title"],
                )
                file = st.file_uploader("资料文件", type=["pdf", "md", "txt", "html", "docx", "xlsx", "json"])
                title = st.text_input("文档标题（可选）")
                url = st.text_input("公开来源 URL（可选）")
                publisher = st.text_input("发布机构")
                published = st.text_input("发布日期 YYYY-MM-DD（可选）")
                effective = st.text_input("生效日期 YYYY-MM-DD（可选）")
                expires = st.text_input("失效日期 YYYY-MM-DD（可选）")
                authority = st.slider("来源等级（由管理员核实）", 0, 5, 0)
                if st.form_submit_button("提交入库", type="primary"):
                    if not file:
                        st.error("请选择文件")
                    else:
                        try:
                            result = call(
                                "POST",
                                "/documents",
                                data={
                                    "kb_id": kb["id"],
                                    "document_id": existing["id"] if existing else "",
                                    "title": title,
                                    "source_url": url,
                                    "publisher": publisher,
                                    "published_on": published,
                                    "effective_on": effective,
                                    "expires_on": expires,
                                    "authority": authority,
                                },
                                files={"file": (file.name, file.getvalue(), file.type)},
                            )
                            st.success("入库任务已提交：" + result["task_id"])
                            if result.get("dispatch_warning"):
                                st.warning(result["dispatch_warning"])
                        except RuntimeError as exc:
                            st.error(str(exc))
        if st.button("刷新入库状态"):
            st.rerun()
        tasks = call("GET", "/tasks", params={"kb_id": kb["id"]})["tasks"]
        st.dataframe(tasks, width="stretch", hide_index=True)
        failed = [task for task in tasks if task["status"] in {"failed", "queued", "processing"}]
        if failed and profile["role"] in {"admin", "editor"}:
            retry = st.selectbox("重试任务", failed, format_func=lambda row: f"{row['id']} · {row['status']}")
            st.caption("运行中的任务仅在超过 30 分钟未更新状态后允许重新领取。")
            if st.button("执行重试"):
                try:
                    call("POST", f"/tasks/{retry['id']}/retry")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
        st.subheader("文档版本")
        if documents:
            document = st.selectbox("查看文档", documents, format_func=lambda row: row["title"])
            versions = call("GET", f"/documents/{document['id']}/versions")["versions"]
            st.dataframe(versions, width="stretch", hide_index=True)
            if len(versions) > 1:
                left, right = st.columns(2)
                old = left.selectbox(
                    "旧版本", versions, index=1, format_func=lambda row: f"v{row['number']} · {row['status']}"
                )
                new = right.selectbox("新版本", versions, format_func=lambda row: f"v{row['number']} · {row['status']}")
                if st.button("比较版本"):
                    st.code(
                        call(
                            "GET",
                            f"/documents/{document['id']}/compare",
                            params={"old_id": old["id"], "new_id": new["id"]},
                        )["diff"],
                        language="diff",
                    )
            if profile["role"] in {"admin", "editor"}:
                confirm = st.checkbox("确认停用当前文档及其检索内容")
                if st.button("停用文档", disabled=not confirm):
                    call("DELETE", f"/documents/{document['id']}")
                    st.rerun()

with kb_tab:
    st.dataframe(kbs, width="stretch", hide_index=True)
    if profile["role"] in {"admin", "editor"}:
        with st.form("create_kb"):
            name = st.text_input("知识库名称")
            description = st.text_area("范围与内容说明")
            category = st.selectbox("知识类型", ["general", "disease", "guideline", "drug", "lab", "hospital"])
            visibility = st.radio(
                "可见范围",
                ["tenant", "restricted"],
                format_func=lambda x: "空间成员可读" if x == "tenant" else "仅授权成员可读",
            )
            if st.form_submit_button("创建知识库"):
                try:
                    call(
                        "POST",
                        "/knowledge-bases",
                        json={"name": name, "description": description, "category": category, "visibility": visibility},
                    )
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
    if profile["role"] == "admin":
        with st.expander("成员与知识库授权"):
            with st.form("member"):
                username = st.text_input("新成员用户名")
                password = st.text_input("新成员初始密码", type="password")
                role = st.selectbox("成员角色", ["viewer", "editor"])
                if st.form_submit_button("创建成员"):
                    try:
                        call("POST", "/users", json={"username": username, "password": password, "role": role})
                        st.success("成员已创建")
                    except RuntimeError as exc:
                        st.error(str(exc))
            members = call("GET", "/users")["users"]
            if kbs and members:
                kb = st.selectbox("授权知识库", kbs, format_func=lambda row: row["name"])
                member = st.selectbox("成员", members, format_func=lambda row: row["username"])
                left, right = st.columns(2)
                if left.button("授予访问"):
                    call("POST", f"/knowledge-bases/{kb['id']}/grants", json={"user_id": member["id"]})
                    st.success("已授权")
                if right.button("撤销访问"):
                    call("DELETE", f"/knowledge-bases/{kb['id']}/grants/{member['id']}")
                    st.success("已撤销显式授权；空间可读知识库仍由可见范围决定。")
    if kbs and profile["role"] in {"admin", "editor"}:
        with st.expander("编辑或归档知识库"):
            target = st.selectbox("管理目标", kbs, format_func=lambda row: row["name"])
            with st.form("edit_kb"):
                edited_name = st.text_input("更新名称", value=target["name"])
                edited_description = st.text_area("更新范围说明", value=target["description"])
                edited_visibility = st.selectbox(
                    "更新可见范围", ["tenant", "restricted"], index=0 if target["visibility"] == "tenant" else 1
                )
                if st.form_submit_button("保存知识库设置"):
                    call(
                        "PUT",
                        f"/knowledge-bases/{target['id']}",
                        json={
                            "name": edited_name,
                            "description": edited_description,
                            "visibility": edited_visibility,
                            "category": target["category"],
                        },
                    )
                    st.rerun()
            archive_confirmed = st.checkbox("确认归档此知识库，其文档将停止参与检索")
            if st.button("归档知识库", disabled=not archive_confirmed):
                call("DELETE", f"/knowledge-bases/{target['id']}")
                st.rerun()

with debug_tab:
    with st.form("search"):
        question = st.text_input("仅检索证据，不生成回答")
        if st.form_submit_button("检索"):
            try:
                st.session_state.search_result = call(
                    "POST",
                    "/retrieval/search",
                    json={"query": question, "kb_ids": [row["id"] for row in selected], "limit": limit, "mode": mode},
                )
            except RuntimeError as exc:
                st.error(str(exc))
    if st.session_state.get("search_result"):
        st.json(st.session_state.search_result)
    if st.session_state.get("last_result"):
        result = st.session_state.last_result
        st.write(f"最近问答：{result['route']} · 检索 {result['attempts']} 次 · {result['latency_ms']} ms")
        st.json(
            {
                "plan": result["plan"],
                "debug": result["debug"],
                "sql_rows": result["sql_rows"],
                "warnings": result["warnings"],
            }
        )
        with st.form("feedback"):
            rating = st.slider("回答评分", 1, 5, 3)
            comment = st.text_area("问题与改进意见")
            if st.form_submit_button("提交反馈"):
                call("POST", "/feedback", json={"query_id": result["query_id"], "rating": rating, "comment": comment})
                st.success("反馈已保存")
