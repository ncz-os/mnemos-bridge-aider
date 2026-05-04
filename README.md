# mnemos-bridge-aider

Aider adapter for the MNEMOS bridge abstraction.

This package provides two integration paths for [Aider](https://aider.chat):

- **Path A, sidecar helper script:** the canonical path. Run `mnemos-aider` in a terminal beside Aider and paste the markdown output into your Aider session.
- **Path B, Aider tool adapter:** forward-compatible tooling that exposes MNEMOS MCP tools in OpenAI tool-call shape for Aider versions and plugin setups that can consume them. Aider's plugin API is unstable, so this path is best-effort.

## Install

```bash
pip install mnemos-bridge-aider
```

## Path A: Sidecar CLI

Use this when you want a stable workflow with any Aider version.

```bash
mnemos-aider search "how did we configure the bridge?" --limit 5
mnemos-aider search "project memory" --namespace pythia
mnemos-aider create --content "Aider Path A is the canonical MNEMOS workflow." --category note
mnemos-aider get mem_123
mnemos-aider list --limit 10
mnemos-aider config
```

Typical workflow:

1. Start Aider in your project.
2. In another terminal, run `mnemos-aider search "..."`.
3. Paste the returned markdown into Aider.
4. Ask Aider to use that context while editing.

The CLI uses the MNEMOS REST API at `MNEMOS_BASE`, defaulting to:

```text
http://192.168.207.67:5002
```

## Path B: Aider Tool Adapter

Path B exposes MNEMOS MCP tools in OpenAI tool-call shape, which matches the shape Aider uses internally.

```python
import os

from mnemos_bridge_aider import MnemosAiderAdapter


async def register(coder):
    adapter = await MnemosAiderAdapter.connect(
        "http://192.168.207.67:5003",
        os.environ.get("MNEMOS_MCP_TOKEN"),
    )
    await adapter.register_with_aider(coder)
```

You can also call tools manually:

```python
tools = await adapter.aider_tools()
result = await adapter.handle_tool_call(
    {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "mnemos_search",
            "arguments": "{\"query\": \"bridge notes\"}",
        },
    }
)
```

Path B requires `mnemos-bridge-core>=0.1.0` and `aider-chat>=0.50`. If the concrete core or Aider plugin API changes, the adapter falls back where it can and otherwise leaves a clear runtime error. Treat Path B as forward-compat only until Aider's plugin hooks stabilize.

## Configuration

Environment variables take precedence:

```bash
export MNEMOS_BASE=http://192.168.207.67:5002
export MNEMOS_API_KEY=...
export MNEMOS_MCP_TOKEN=...
```

`~/.mnemos/config.toml` is used as a fallback for the sidecar CLI:

```toml
base = "http://192.168.207.67:5002"
api_key = "..."

[mnemos]
mcp_url = "http://192.168.207.67:5003"
mcp_token = "..."
```

`MNEMOS_API_KEY` is sent to the REST API as a bearer token. `MNEMOS_MCP_TOKEN` is used by Path B for the MCP HTTP/SSE endpoint.

## Development

```bash
python -m pytest tests/test_cli_offline.py tests/test_adapter_offline.py
```

The live integration test is skipped unless `MNEMOS_TEST_BASE` is set. It only covers Path A because Aider plugin behavior varies across Aider versions.
