import argparse
import json
import time

from sqlalchemy import select

from app.core.config import ROOT
from app.models import IngestionTask, Version
from app.runtime import Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inline", action="store_true", help="Run in the current process instead of the Celery queue")
    parser.add_argument("--wait", action="store_true", help="Wait up to 15 minutes for all tasks")
    args = parser.parse_args()
    runtime = Runtime()
    try:
        token = runtime.identity.login(
            runtime.settings.admin_username, runtime.settings.admin_password.get_secret_value()
        )
        user = runtime.identity.resolve(token)
        manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
        tasks = []
        for entry in manifest["documents"]:
            available = runtime.kbs.list(user)
            kb = next((kb for kb in available if kb.name == entry["kb"]), None)
            if kb is None:
                kb = runtime.kbs.create(
                    user,
                    {
                        "name": entry["kb"],
                        "category": entry["category"],
                        "description": "公开来源阅读资料与知识索引",
                        "visibility": "tenant",
                    },
                )
            doc = next((doc for doc in runtime.documents.list(user, kb.id) if doc.title == entry["title"]), None)
            content = (ROOT / "data/samples" / entry["file"]).read_bytes()
            result = runtime.documents.upload(
                user,
                kb.id,
                entry["file"],
                content,
                {
                    key: value
                    for key, value in entry.items()
                    if key in {"title", "source_url", "publisher", "authority"}
                },
                doc.id if doc else None,
            )
            tasks.append(result["task_id"])
            if args.inline:
                runtime.pipeline.run(result["task_id"])
            else:
                runtime.dispatch(result["task_id"])
            print(entry["title"], result["task_id"], flush=True)
        if args.wait:
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                with runtime.db.session() as session:
                    states = session.scalars(select(IngestionTask).where(IngestionTask.id.in_(tasks))).all()
                    if all(task.status in {"succeeded", "failed", "cancelled"} for task in states):
                        print(
                            json.dumps(
                                {task.id: {"status": task.status, "error": task.error} for task in states},
                                ensure_ascii=False,
                            )
                        )
                        if any(task.status != "succeeded" for task in states):
                            raise SystemExit(1)
                        return
                time.sleep(2)
            raise TimeoutError("等待入库完成超时；任务仍保存在数据库，可查询 /tasks")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
