"""Path A: sidecar CLI for using MNEMOS alongside Aider."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import httpx

DEFAULT_BASE = "http://192.168.207.67:5002"
CONFIG_PATH = Path("~/.mnemos/config.toml").expanduser()


@dataclass(frozen=True)
class MnemosConfig:
    """Resolved REST configuration for the sidecar helper."""

    base: str
    api_key: str | None
    config_path: Path = CONFIG_PATH
    config_found: bool = False


def _load_config_file(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    if not isinstance(data, dict):
        return {}

    mnemos_section = data.get("mnemos")
    if isinstance(mnemos_section, dict):
        merged = {**data, **mnemos_section}
        return merged
    return data


def load_config() -> MnemosConfig:
    """Resolve config from env first, then ~/.mnemos/config.toml, then defaults."""

    file_data = _load_config_file(CONFIG_PATH)
    base = (
        os.getenv("MNEMOS_BASE")
        or file_data.get("base")
        or file_data.get("rest_base")
        or file_data.get("url")
        or DEFAULT_BASE
    )
    api_key = os.getenv("MNEMOS_API_KEY") or file_data.get("api_key") or file_data.get("token")

    return MnemosConfig(
        base=str(base).rstrip("/"),
        api_key=str(api_key) if api_key else None,
        config_found=CONFIG_PATH.exists(),
    )


def _headers(config: MnemosConfig) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _client(config: MnemosConfig) -> httpx.Client:
    return httpx.Client(base_url=config.base, headers=_headers(config), timeout=30.0)


def _request_json(method: str, path: str, **kwargs: Any) -> Any:
    config = load_config()
    try:
        with _client(config) as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise click.ClickException(
            f"MNEMOS request failed: HTTP {exc.response.status_code} {exc.response.text}"
        ) from exc
    except httpx.RequestError as exc:
        raise click.ClickException(f"MNEMOS request failed: {exc}") from exc


def _coerce_memories(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item if isinstance(item, dict) else {"content": str(item)} for item in payload]
    if not isinstance(payload, dict):
        return [{"content": str(payload)}]

    for key in ("memories", "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"content": str(item)} for item in value]
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return [
                item if isinstance(item, dict) else {"content": str(item)}
                for item in value["items"]
            ]

    if any(key in payload for key in ("id", "memory_id", "content", "text")):
        return [payload]
    return []


def _memory_id(memory: dict[str, Any]) -> str:
    return str(memory.get("id") or memory.get("memory_id") or memory.get("uuid") or "unknown")


def _memory_content(memory: dict[str, Any]) -> str:
    content = memory.get("content")
    if content is None:
        content = memory.get("text")
    if content is None:
        content = memory.get("value")
    return str(content or "").strip()


def _metadata_lines(memory: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    fields = [
        ("score", "Score"),
        ("namespace", "Namespace"),
        ("category", "Category"),
        ("created_at", "Created"),
        ("updated_at", "Updated"),
    ]
    for key, label in fields:
        value = memory.get(key)
        if value is not None and value != "":
            lines.append(f"- {label}: `{value}`")
    return lines


def _format_memory(memory: dict[str, Any], *, index: int | None = None) -> str:
    title = _memory_id(memory)
    heading = f"## {index}. {title}" if index is not None else f"# MNEMOS memory {title}"
    parts = [heading]
    metadata = _metadata_lines(memory)
    if metadata:
        parts.extend(metadata)
    content = _memory_content(memory)
    if content:
        parts.extend(["", content])
    return "\n".join(parts).strip()


def format_search(query: str, payload: Any) -> str:
    memories = _coerce_memories(payload)
    if not memories:
        return f"# MNEMOS search: {query}\n\nNo memories found."

    parts = [f"# MNEMOS search: {query}", "", f"Found {len(memories)} memories."]
    for index, memory in enumerate(memories, start=1):
        parts.extend(["", _format_memory(memory, index=index)])
    return "\n".join(parts).strip()


def format_created(payload: Any) -> str:
    memories = _coerce_memories(payload)
    memory = memories[0] if memories else (payload if isinstance(payload, dict) else {})
    parts = ["# MNEMOS memory created", f"- ID: `{_memory_id(memory)}`"]
    for line in _metadata_lines(memory):
        if not line.startswith("- Score:"):
            parts.append(line)
    content = _memory_content(memory)
    if content:
        parts.extend(["", content])
    return "\n".join(parts).strip()


def format_list(payload: Any) -> str:
    memories = _coerce_memories(payload)
    if not memories:
        return "# MNEMOS memories\n\nNo memories found."

    parts = ["# MNEMOS memories", "", f"Found {len(memories)} memories."]
    for index, memory in enumerate(memories, start=1):
        parts.extend(["", _format_memory(memory, index=index)])
    return "\n".join(parts).strip()


def _echo_markdown(text: str) -> None:
    click.echo(text.rstrip())


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Use MNEMOS from an Aider sidecar terminal."""


@main.command()
@click.argument("query")
@click.option("--limit", default=5, show_default=True, type=click.IntRange(min=1))
@click.option("--namespace", "namespace", default=None)
def search(query: str, limit: int, namespace: str | None) -> None:
    """Search MNEMOS memories and print paste-ready markdown."""

    body: dict[str, Any] = {"query": query, "limit": limit}
    if namespace:
        body["namespace"] = namespace
    payload = _request_json("POST", "/memories/search", json=body)
    _echo_markdown(format_search(query, payload))


@main.command()
@click.option("--content", required=True, help="Memory content to create.")
@click.option("--category", default=None)
def create(content: str, category: str | None) -> None:
    """Create a MNEMOS memory."""

    body: dict[str, Any] = {"content": content}
    if category:
        body["category"] = category
    payload = _request_json("POST", "/memories", json=body)
    _echo_markdown(format_created(payload))


@main.command(name="get")
@click.argument("memory_id")
def get_memory(memory_id: str) -> None:
    """Fetch one MNEMOS memory by id."""

    payload = _request_json("GET", f"/memories/{memory_id}")
    memories = _coerce_memories(payload)
    memory = memories[0] if memories else {"id": memory_id}
    _echo_markdown(_format_memory(memory))


@main.command(name="list")
@click.option("--limit", default=10, show_default=True, type=click.IntRange(min=1))
def list_memories(limit: int) -> None:
    """List recent MNEMOS memories."""

    payload = _request_json("GET", "/memories", params={"limit": limit})
    _echo_markdown(format_list(payload))


@main.command()
def config() -> None:
    """Show resolved MNEMOS sidecar configuration."""

    resolved = load_config()
    lines = [
        "# MNEMOS Aider configuration",
        f"- REST base: `{resolved.base}`",
        f"- API key: `{'configured' if resolved.api_key else 'not configured'}`",
        f"- Config file: `{resolved.config_path}` ({'found' if resolved.config_found else 'not found'})",
    ]
    _echo_markdown("\n".join(lines))


if __name__ == "__main__":
    main()
