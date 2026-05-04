from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mnemos_bridge_aider import cli


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"
        self.status_code = 200
        self.text = "OK"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    requests = []
    payloads = {}

    def __init__(self, base_url, headers, timeout):
        self.base_url = base_url
        self.headers = headers
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs, self.base_url, self.headers))
        return FakeResponse(self.payloads[(method, path)])


def setup_fake(monkeypatch, tmp_path: Path, payloads):
    FakeClient.requests = []
    FakeClient.payloads = payloads
    monkeypatch.setattr(cli.httpx, "Client", FakeClient)
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "missing.toml")
    monkeypatch.setenv("MNEMOS_BASE", "http://mnemos.test")
    monkeypatch.setenv("MNEMOS_API_KEY", "secret")


def test_search_formats_markdown(monkeypatch, tmp_path):
    setup_fake(
        monkeypatch,
        tmp_path,
        {
            ("POST", "/memories/search"): {
                "memories": [
                    {
                        "id": "mem-1",
                        "content": "Use Aider with the MNEMOS sidecar.",
                        "score": 0.91,
                        "namespace": "docs",
                    }
                ]
            }
        },
    )

    result = CliRunner().invoke(cli.main, ["search", "aider sidecar", "--limit", "3", "--namespace", "docs"])

    assert result.exit_code == 0
    assert "# MNEMOS search: aider sidecar" in result.output
    assert "Found 1 memories." in result.output
    assert "## 1. mem-1" in result.output
    assert "Use Aider with the MNEMOS sidecar." in result.output
    method, path, kwargs, base_url, headers = FakeClient.requests[0]
    assert (method, path, base_url) == ("POST", "/memories/search", "http://mnemos.test")
    assert headers["Authorization"] == "Bearer secret"
    assert kwargs["json"] == {"query": "aider sidecar", "limit": 3, "namespace": "docs"}


def test_create_formats_created_memory(monkeypatch, tmp_path):
    setup_fake(
        monkeypatch,
        tmp_path,
        {
            ("POST", "/memories"): {
                "id": "mem-2",
                "content": "Aider Path A is canonical.",
                "category": "integration",
            }
        },
    )

    result = CliRunner().invoke(
        cli.main,
        ["create", "--content", "Aider Path A is canonical.", "--category", "integration"],
    )

    assert result.exit_code == 0
    assert "# MNEMOS memory created" in result.output
    assert "- ID: `mem-2`" in result.output
    assert "- Category: `integration`" in result.output
    assert "Aider Path A is canonical." in result.output
    assert FakeClient.requests[0][2]["json"] == {
        "content": "Aider Path A is canonical.",
        "category": "integration",
    }


def test_get_formats_memory(monkeypatch, tmp_path):
    setup_fake(
        monkeypatch,
        tmp_path,
        {
            ("GET", "/memories/mem-3"): {
                "id": "mem-3",
                "content": "Retrieved content.",
                "namespace": "default",
            }
        },
    )

    result = CliRunner().invoke(cli.main, ["get", "mem-3"])

    assert result.exit_code == 0
    assert "# MNEMOS memory mem-3" in result.output
    assert "- Namespace: `default`" in result.output
    assert "Retrieved content." in result.output


def test_list_formats_recent_memories(monkeypatch, tmp_path):
    setup_fake(
        monkeypatch,
        tmp_path,
        {
            ("GET", "/memories"): {
                "memories": [
                    {"id": "mem-4", "content": "First"},
                    {"id": "mem-5", "content": "Second"},
                ]
            }
        },
    )

    result = CliRunner().invoke(cli.main, ["list", "--limit", "2"])

    assert result.exit_code == 0
    assert "# MNEMOS memories" in result.output
    assert "Found 2 memories." in result.output
    assert "## 1. mem-4" in result.output
    assert "## 2. mem-5" in result.output
    assert FakeClient.requests[0][2]["params"] == {"limit": 2}


def test_config_uses_env_and_masks_key(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setenv("MNEMOS_BASE", "http://mnemos.local")
    monkeypatch.setenv("MNEMOS_API_KEY", "do-not-print")

    result = CliRunner().invoke(cli.main, ["config"])

    assert result.exit_code == 0
    assert "# MNEMOS Aider configuration" in result.output
    assert "- REST base: `http://mnemos.local`" in result.output
    assert "- API key: `configured`" in result.output
    assert "do-not-print" not in result.output
