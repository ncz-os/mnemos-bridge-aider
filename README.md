# mnemos-bridge-aider

Aider adapter for the MNEMOS bridge abstraction.

This package provides two integration paths for [Aider](https://aider.chat):

- **Path A, sidecar helper script:** the canonical path. Run `mnemos-aider` in a terminal beside Aider and paste the markdown output into your Aider session.
- **Path B, Aider integration:** a slash-command shim for Aider 0.86.x that adds `/mnemos-search` and `/mnemos-create` inside the Aider session.

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

## Path B: Aider integration

Path B currently ships as a slash-command shim. Aider `0.86.2` exposes commands by scanning `aider.commands.Commands` for `cmd_*` methods, but it does not expose a stable plugin namespace, documented extension entry point, or public Coder tool-registration hook. The shim monkey-patches that command class at startup.

What works:

- `/mnemos-search <query>` calls `POST /memories/search`.
- `/mnemos-create <content> [category]` calls `POST /memories`.
- Results are printed in the Aider session and also added to the current chat context when Aider exposes `coder.cur_messages`.

It uses the MNEMOS REST API at `MNEMOS_BASE`, defaulting to `http://192.168.207.67:5002`. The bearer token is read from `MNEMOS_API_KEY` first, then `MNEMOS_BEARER_TOKEN`.

Copy-paste invocation:

```bash
export MNEMOS_API_KEY=...
python3 -c "import mnemos_bridge_aider.path_b_shim as s; s.install(); from aider.main import main; raise SystemExit(main())" -- .
```

Inside Aider:

```text
/mnemos-search "how did we configure the bridge?"
/mnemos-create "Aider Path B slash commands are installed." integration
```

The stable adapter API remains available for launchers that receive a live Coder object:

```python
from mnemos_bridge_aider import MnemosAiderAdapter, register_with_aider

commands = await MnemosAiderAdapter().aider_tools()
register_with_aider(coder)
```

Path B was implemented and tested against `aider-chat==0.86.2`. If Aider adds a documented plugin/tool API later, this path can move from command patching to native tool registration.

## Configuration

Environment variables take precedence:

```bash
export MNEMOS_BASE=http://192.168.207.67:5002
export MNEMOS_API_KEY=...
export MNEMOS_BEARER_TOKEN=...
```

`~/.mnemos/config.toml` is used as a fallback for the sidecar CLI:

```toml
base = "http://192.168.207.67:5002"
api_key = "..."

[mnemos]
rest_base = "http://192.168.207.67:5002"
```

`MNEMOS_API_KEY` is sent to the REST API as a bearer token. Path B also accepts `MNEMOS_BEARER_TOKEN`.

## Development

```bash
python -m pytest tests/test_cli_offline.py tests/test_adapter_offline.py
```

The live integration test is skipped unless `MNEMOS_TEST_BASE` is set. It only covers Path A because Aider plugin behavior varies across Aider versions.
