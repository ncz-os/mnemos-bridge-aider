"""Slash-command shim for Aider 0.86.x Path B integration."""

from __future__ import annotations

import os
import shlex
from typing import Any

import httpx

from .cli import DEFAULT_BASE, format_created, format_search

COMMAND_NAMES = ["/mnemos-search", "/mnemos-create"]
DEFAULT_SEARCH_LIMIT = 5


def _base_url() -> str:
    return os.getenv("MNEMOS_BASE", DEFAULT_BASE).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = os.getenv("MNEMOS_API_KEY") or os.getenv("MNEMOS_BEARER_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(method: str, path: str, **kwargs: Any) -> Any:
    with httpx.Client(base_url=_base_url(), headers=_headers(), timeout=30.0) as client:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()


def _tool_output(command: Any, text: str) -> None:
    output = getattr(getattr(command, "io", None), "tool_output", None)
    if output is not None:
        output(text.rstrip())
    else:
        print(text.rstrip())


def _tool_error(command: Any, text: str) -> None:
    error = getattr(getattr(command, "io", None), "tool_error", None)
    if error is not None:
        error(text)
    else:
        print(text)


def _add_to_chat(command: Any, markdown: str) -> None:
    coder = getattr(command, "coder", None)
    cur_messages = getattr(coder, "cur_messages", None)
    if isinstance(cur_messages, list):
        cur_messages.extend(
            [
                {"role": "user", "content": f"MNEMOS result:\n\n{markdown.rstrip()}"},
                {"role": "assistant", "content": "Ok."},
            ]
        )


def _emit_result(command: Any, markdown: str) -> str:
    markdown = markdown.rstrip()
    _tool_output(command, markdown)
    _add_to_chat(command, markdown)
    return markdown


def _format_request_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        return f"MNEMOS request failed: HTTP {response.status_code} {response.text}"
    if isinstance(exc, httpx.RequestError):
        return f"MNEMOS request failed: {exc}"
    return f"MNEMOS command failed: {exc}"


def _search_limit() -> int:
    raw_limit = os.getenv("MNEMOS_AIDER_SEARCH_LIMIT")
    if raw_limit is None:
        return DEFAULT_SEARCH_LIMIT
    try:
        return max(1, int(raw_limit))
    except ValueError:
        return DEFAULT_SEARCH_LIMIT


def _parse_create_args(args: str) -> tuple[str, str | None]:
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        raise ValueError(f"Unable to parse arguments: {exc}") from exc

    if not parts:
        raise ValueError("Usage: /mnemos-create <content> [category]")
    if len(parts) == 1:
        return parts[0], None
    return " ".join(parts[:-1]), parts[-1]


def cmd_mnemos_search(command: Any, args: str) -> str | None:
    """Search MNEMOS memories and add the result to chat context."""

    query = args.strip()
    if not query:
        _tool_error(command, "Usage: /mnemos-search <query>")
        return None

    try:
        payload = _request_json(
            "POST",
            "/memories/search",
            json={"query": query, "limit": _search_limit()},
        )
    except Exception as exc:
        _tool_error(command, _format_request_error(exc))
        return None

    return _emit_result(command, format_search(query, payload))


def cmd_mnemos_create(command: Any, args: str) -> str | None:
    """Create a MNEMOS memory and add the result to chat context."""

    try:
        content, category = _parse_create_args(args)
    except ValueError as exc:
        _tool_error(command, str(exc))
        return None

    body: dict[str, Any] = {"content": content}
    if category:
        body["category"] = category

    try:
        payload = _request_json("POST", "/memories", json=body)
    except Exception as exc:
        _tool_error(command, _format_request_error(exc))
        return None

    return _emit_result(command, format_created(payload))


def install(commands_cls: type[Any] | None = None) -> list[str]:
    """Install MNEMOS slash commands on Aider's Commands class.

    Passing ``commands_cls`` is intended for tests or custom launchers. With no
    argument, the installed ``aider.commands.Commands`` class is patched.
    """

    if commands_cls is None:
        try:
            from aider.commands import Commands as commands_cls
        except ImportError as exc:
            raise RuntimeError("Path B slash-command shim requires aider-chat>=0.86") from exc

    if getattr(commands_cls, "_mnemos_bridge_aider_installed", False):
        return COMMAND_NAMES.copy()

    setattr(commands_cls, "cmd_mnemos_search", cmd_mnemos_search)
    setattr(commands_cls, "cmd_mnemos_create", cmd_mnemos_create)
    setattr(commands_cls, "_mnemos_bridge_aider_installed", True)
    return COMMAND_NAMES.copy()


def main(argv: list[str] | None = None) -> int | None:
    """Launch Aider with the Path B slash-command shim installed."""

    install()
    from aider.main import main as aider_main

    return aider_main(argv)
