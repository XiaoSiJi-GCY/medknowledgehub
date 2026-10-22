import httpx

from app.core.errors import HubError


class MinerUClient:
    """Self-hosted MinerU V1 JSON response; native-text parsers remain separate."""

    def __init__(self, settings):
        self.url = settings.mineru_api_url.rstrip("/")
        self.key = settings.mineru_api_key.get_secret_value()

    def parse(self, path):
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        with httpx.Client(timeout=330, follow_redirects=False) as client:
            with path.open("rb") as file:
                response = client.post(
                    self.url + "/v1/file_parse",
                    headers=headers,
                    params={"response_format": "json", "output_formats": "md,json", "wait_timeout": 300},
                    files={"files": (path.name, file, "application/pdf")},
                )
            if response.status_code == 202:
                raise HubError("MinerU 任务超过同步等待时间；稍后重试或提高解析服务能力。", 503)
            response.raise_for_status()
            result = response.json()
        blocks = []
        for file in result.get("files", []):
            content = file.get("content", {})
            if isinstance(content, dict):
                for name, value in content.items():
                    if isinstance(value, str) and ("markdown" in name or name.endswith(".md") or name == "md"):
                        blocks.append({"text": value, "page": None, "bbox": None, "kind": "text", "section": ""})
        if not blocks:
            raise HubError("MinerU 响应没有可用 Markdown，请核对 V1 服务的输出格式。", 502)
        return blocks
