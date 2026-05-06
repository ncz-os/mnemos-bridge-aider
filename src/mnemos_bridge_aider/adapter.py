"""Path B: Aider slash-command integration.

Aider 0.86.x does not expose a stable plugin/tool registration API. The public
adapter surface therefore installs the Path B slash-command shim while keeping
the older direct MCP tool-call helpers available for custom launchers.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from . import path_b_shim

if TYPE_CHECKING:  # pragma: no cover - documentation-only imports.
    from mnemos_bridge_core import McpClient as CoreMcpClient
    from mnemos_bridge_core import SchemaTranslator as CoreSchemaTranslator


class McpClientProtocol(Protocol):
    async def list_tools(self) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

    async def aclose(self) -> None: ...


def _maybe_await(value: Any) -> Awaitable[Any] | Any:
    return value


async def _resolve(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class _FallbackSchemaTranslator:
    """Small OpenAI tool translator used when mnemos-bridge-core is unavailable.

    TODO: Remove this compatibility shim once the concrete SchemaTranslator API
    in mnemos-bridge-core is stable and available in all supported runtimes.
    """

    @staticmethod
    def to_openai(tools: Any) -> list[dict[str, Any]]:
        normalized = _coerce_tools(tools)
        openai_tools: list[dict[str, Any]] = []
        for tool in normalized:
            name = str(tool.get("name") or tool.get("id") or "")
            if not name:
                continue
            input_schema = (
                tool.get("inputSchema")
                or tool.get("input_schema")
                or tool.get("parameters")
                or {"type": "object", "properties": {}}
            )
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(tool.get("description") or ""),
                        "parameters": input_schema,
                    },
                }
            )
        return openai_tools


class _HttpMcpClient:
    """Minimal JSON-RPC-over-HTTP MCP client for MNEMOS.

    MNEMOS deployments may expose richer HTTP/SSE behavior. This fallback keeps
    the adapter usable without depending on unknown core internals; production
    users should rely on mnemos-bridge-core's MCP client when available.
    """

    def __init__(self, mcp_url: str, mcp_token: str | None, *, timeout: float = 30) -> None:
        headers = {"Accept": "application/json"}
        if mcp_token:
            headers["Authorization"] = f"Bearer {mcp_token}"
        self._client = httpx.AsyncClient(base_url=mcp_url, headers=headers, timeout=timeout)
        self._request_id = 0

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        response = await self._client.post(
            "",
            json={
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params or {},
            },
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"MCP error from {method}: {payload['error']}")
        return payload.get("result", payload) if isinstance(payload, dict) else payload

    async def list_tools(self) -> Any:
        return await self._rpc("tools/list")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self._rpc("tools/call", {"name": name, "arguments": arguments})

    async def aclose(self) -> None:
        await self._client.aclose()


def _load_core_symbol(name: str) -> Any | None:
    try:
        module = __import__("mnemos_bridge_core", fromlist=[name])
    except ImportError:
        return None
    return getattr(module, name, None)


def _coerce_tools(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("tools", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _coerce_tools(value)
                if nested:
                    return nested
    return []


def _normalize_tool_call(tool_call: Any) -> tuple[str, dict[str, Any], str | None]:
    if hasattr(tool_call, "model_dump"):
        tool_call = tool_call.model_dump()
    elif not isinstance(tool_call, dict) and hasattr(tool_call, "__dict__"):
        tool_call = vars(tool_call)

    if not isinstance(tool_call, dict):
        raise TypeError("tool_call must be a dict-like OpenAI tool call")

    call_id = tool_call.get("id") or tool_call.get("tool_call_id")
    function = tool_call.get("function") or {}
    if hasattr(function, "model_dump"):
        function = function.model_dump()
    elif not isinstance(function, dict) and hasattr(function, "__dict__"):
        function = vars(function)

    name = tool_call.get("name") or function.get("name")
    arguments = tool_call.get("arguments", function.get("arguments", {}))
    if isinstance(arguments, str):
        arguments = json.loads(arguments or "{}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise TypeError("tool_call arguments must be a JSON object")
    if not name:
        raise ValueError("tool_call is missing function name")
    return str(name), arguments, str(call_id) if call_id else None


def _format_tool_result(call_id: str | None, name: str, result: Any) -> dict[str, Any]:
    content = result
    if isinstance(result, dict) and "content" in result:
        content = result["content"]

    if not isinstance(content, str):
        content = json.dumps(content, indent=2, sort_keys=True)

    response: dict[str, Any] = {
        "role": "tool",
        "name": name,
        "content": content,
    }
    if call_id:
        response["tool_call_id"] = call_id
    return response


class MnemosAiderAdapter:
    """Expose the MNEMOS Path B shim through the stable adapter API."""

    def __init__(
        self,
        mcp_client: McpClientProtocol | CoreMcpClient | None = None,
        *,
        translator: type[CoreSchemaTranslator] | Any | None = None,
        mcp_url: str | None = None,
    ) -> None:
        self._mcp = mcp_client
        self._translator = translator
        self.mcp_url = mcp_url
        self._tools_cache: list[str] | None = None

    @classmethod
    async def connect(
        cls,
        mcp_url: str,
        mcp_token: str | None,
        *,
        timeout: float = 30,
    ) -> "MnemosAiderAdapter":
        """Connect to MNEMOS MCP and return an Aider adapter.

        mnemos-bridge-core is preferred when installed. If its McpClient API has
        drifted, this falls back to a tiny HTTP JSON-RPC client so importing and
        basic usage remain predictable.
        """

        core_client_cls = _load_core_symbol("McpClient")
        translator = _load_core_symbol("SchemaTranslator")

        if core_client_cls is not None:
            try:
                if hasattr(core_client_cls, "connect"):
                    mcp_client = await _resolve(
                        core_client_cls.connect(mcp_url, mcp_token, timeout=timeout)
                    )
                else:
                    mcp_client = core_client_cls(mcp_url, mcp_token, timeout=timeout)
                return cls(mcp_client, translator=translator, mcp_url=mcp_url)
            except Exception:
                # Core internals are not part of this scaffold's contract yet.
                # Fall back to the minimal client instead of breaking Aider startup.
                pass

        return cls(_HttpMcpClient(mcp_url, mcp_token, timeout=timeout), translator=translator, mcp_url=mcp_url)

    async def aider_tools(self) -> list[str]:
        """Return Path B slash-command names for Aider 0.86.x."""

        return path_b_shim.COMMAND_NAMES.copy()

    async def register_with_aider(self, coder: Any) -> None:
        """Best-effort registration against Aider coder objects.

        Aider 0.86.x has no stable plugin/tool registration surface. Path B
        therefore installs slash commands on the active Commands class.
        """

        register_with_aider(coder)
        try:
            setattr(coder, "mnemos_aider_adapter", self)
        except Exception:
            pass

    async def handle_tool_call(self, tool_call: Any) -> dict[str, Any]:
        """Handle an OpenAI-shaped tool call from Aider."""

        if self._mcp is None:
            raise RuntimeError("No MCP client configured for direct tool-call handling")
        name, arguments, call_id = _normalize_tool_call(tool_call)
        result = await _resolve(self._mcp.call_tool(name, arguments))
        return _format_tool_result(call_id, name, result)

    async def aclose(self) -> None:
        """Close the underlying MCP client if it exposes an async close hook."""

        close = getattr(self._mcp, "aclose", None)
        if close is not None:
            await _resolve(close())


def register_with_aider(coder: Any) -> list[str]:
    """Register Path B slash commands with a live Aider Coder instance."""

    commands = getattr(coder, "commands", None)
    if commands is not None:
        return path_b_shim.install(type(commands))
    return path_b_shim.install()
