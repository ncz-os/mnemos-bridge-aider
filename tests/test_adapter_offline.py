from __future__ import annotations

import json

import pytest

from mnemos_bridge_aider import path_b_shim
from mnemos_bridge_aider.adapter import MnemosAiderAdapter, register_with_aider


class FakeMcpClient:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def list_tools(self):
        return {
            "tools": [
                {
                    "name": "mnemos_search",
                    "description": "Search MNEMOS memories.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }
            ]
        }

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": f"searched for {arguments['query']}"}

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_aider_tools_returns_path_b_command_names():
    adapter = MnemosAiderAdapter()

    tools = await adapter.aider_tools()

    assert tools == ["/mnemos-search", "/mnemos-create"]


@pytest.mark.asyncio
async def test_handle_tool_call_round_trips_openai_shape():
    fake = FakeMcpClient()
    adapter = MnemosAiderAdapter(fake)

    result = await adapter.handle_tool_call(
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "mnemos_search",
                "arguments": json.dumps({"query": "aider"}),
            },
        }
    )

    assert fake.calls == [("mnemos_search", {"query": "aider"})]
    assert result == {
        "role": "tool",
        "name": "mnemos_search",
        "tool_call_id": "call-1",
        "content": "searched for aider",
    }


@pytest.mark.asyncio
async def test_register_with_aider_patches_coder_commands():
    class FakeCommands:
        pass

    class FakeCoder:
        def __init__(self):
            self.commands = FakeCommands()

    coder = FakeCoder()
    adapter = MnemosAiderAdapter()

    await adapter.register_with_aider(coder)

    assert hasattr(FakeCommands, "cmd_mnemos_search")
    assert hasattr(FakeCommands, "cmd_mnemos_create")
    assert coder.mnemos_aider_adapter is adapter
    assert register_with_aider(coder) == ["/mnemos-search", "/mnemos-create"]


@pytest.mark.asyncio
async def test_aclose_delegates_to_client():
    fake = FakeMcpClient()
    adapter = MnemosAiderAdapter(fake)

    await adapter.aclose()

    assert fake.closed is True


class FakeIo:
    def __init__(self):
        self.outputs = []
        self.errors = []

    def tool_output(self, text):
        self.outputs.append(text)

    def tool_error(self, text):
        self.errors.append(text)


class FakeCoderForCommands:
    def __init__(self):
        self.cur_messages = []


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


class FakeHttpxClient:
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


def setup_path_b_http(monkeypatch, payloads):
    FakeHttpxClient.requests = []
    FakeHttpxClient.payloads = payloads
    monkeypatch.setattr(path_b_shim.httpx, "Client", FakeHttpxClient)
    monkeypatch.setenv("MNEMOS_BASE", "http://mnemos.test")


def test_path_b_search_command_calls_mnemos(monkeypatch):
    class FakeCommands:
        def __init__(self):
            self.io = FakeIo()
            self.coder = FakeCoderForCommands()

    setup_path_b_http(
        monkeypatch,
        {
            ("POST", "/memories/search"): {
                "memories": [
                    {
                        "id": "mem-1",
                        "content": "Aider Path B slash commands are installed.",
                        "score": 0.88,
                    }
                ]
            }
        },
    )
    monkeypatch.delenv("MNEMOS_API_KEY", raising=False)
    monkeypatch.setenv("MNEMOS_BEARER_TOKEN", "bearer-secret")
    path_b_shim.install(FakeCommands)

    commands = FakeCommands()
    result = commands.cmd_mnemos_search("aider path b")

    assert "# MNEMOS search: aider path b" in result
    assert "Aider Path B slash commands are installed." in result
    assert commands.io.outputs == [result]
    assert "MNEMOS result:" in commands.coder.cur_messages[0]["content"]
    method, path, kwargs, base_url, headers = FakeHttpxClient.requests[0]
    assert (method, path, base_url) == ("POST", "/memories/search", "http://mnemos.test")
    assert headers["Authorization"] == "Bearer bearer-secret"
    assert kwargs["json"] == {"query": "aider path b", "limit": 5}


def test_path_b_create_command_calls_mnemos(monkeypatch):
    class FakeCommands:
        def __init__(self):
            self.io = FakeIo()
            self.coder = FakeCoderForCommands()

    setup_path_b_http(
        monkeypatch,
        {
            ("POST", "/memories"): {
                "id": "mem-2",
                "content": "Remember the shim invocation.",
                "category": "integration",
            }
        },
    )
    monkeypatch.setenv("MNEMOS_API_KEY", "api-secret")
    monkeypatch.delenv("MNEMOS_BEARER_TOKEN", raising=False)
    path_b_shim.install(FakeCommands)

    commands = FakeCommands()
    result = commands.cmd_mnemos_create('"Remember the shim invocation." integration')

    assert "# MNEMOS memory created" in result
    assert "- Category: `integration`" in result
    assert commands.io.outputs == [result]
    method, path, kwargs, base_url, headers = FakeHttpxClient.requests[0]
    assert (method, path, base_url) == ("POST", "/memories", "http://mnemos.test")
    assert headers["Authorization"] == "Bearer api-secret"
    assert kwargs["json"] == {
        "content": "Remember the shim invocation.",
        "category": "integration",
    }
