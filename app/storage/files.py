from pathlib import Path

from app.core.errors import HubError


def resolve_raw(settings, stored_path):
    """Keep metadata portable between native Windows and container /app/data mounts."""
    portable = stored_path.replace("\\", "/")
    if "/raw/" in portable:
        portable = "raw/" + portable.rsplit("/raw/", 1)[1]
    root = settings.data_path.resolve()
    path = (root / portable).resolve()
    if not path.is_relative_to(root):
        raise HubError("原始文件路径不在项目数据目录内", 500)
    return path
