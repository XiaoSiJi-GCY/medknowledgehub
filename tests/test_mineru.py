import httpx
import pytest

from app.clients.mineru import MinerUClient
from app.core.config import Settings
from app.core.errors import HubError


def test_mineru_v1_multipart_and_markdown_contract(tmp_path, monkeypatch):
    file = tmp_path / "scan.pdf"
    file.write_bytes(b"%PDF-test")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"files": [{"content": {"markdown": "# Parsed source\nSource text."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)
    parser = MinerUClient(
        Settings(_env_file=None, mineru_api_url="http://parser.local", mineru_api_key="contract-test-key")
    )
    result = parser.parse(file)
    assert result[0]["text"].startswith("# Parsed source")
    assert seen[0].url.path == "/v1/file_parse"
    assert seen[0].headers["authorization"] == "Bearer contract-test-key"


def test_mineru_async_timeout_is_not_misreported_as_success(tmp_path, monkeypatch):
    file = tmp_path / "scan.pdf"
    file.write_bytes(b"%PDF-test")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(202, json={"task_id": "waiting"}))
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client)
    with pytest.raises(HubError, match="等待时间"):
        MinerUClient(Settings(_env_file=None, mineru_api_url="http://parser.local")).parse(file)
