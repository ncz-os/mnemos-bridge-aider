from __future__ import annotations

import json

import pytest

from mnemos_bridge_aider.adapter import MnemosAiderAdapter


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
async def test_aider_tools_returns_openai_shape():
    adapter = MnemosAiderAdapter(FakeMcpClient())

    tools = await adapter.aider_tools()

    assert tools == [
        {
            "type": "function",
            "function": {
                "name": "mnemos_search",
                "description": "Search MNEMOS memories.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]


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
async def test_register_with_aider_extends_tool_list():
    class FakeCoder:
        def __init__(self):
            self.tools = []

    coder = FakeCoder()
    adapter = MnemosAiderAdapter(FakeMcpClient())

    await adapter.register_with_aider(coder)

    assert len(coder.tools) == 1
    assert coder.tools[0]["function"]["name"] == "mnemos_search"
    assert coder.mnemos_aider_adapter is adapter


@pytest.mark.asyncio
async def test_aclose_delegates_to_client():
    fake = FakeMcpClient()
    adapter = MnemosAiderAdapter(fake)

    await adapter.aclose()

    assert fake.closed is True
