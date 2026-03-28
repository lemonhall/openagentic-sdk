# OpenAgentic SDK (Python)

Pure-Python, open-source Agent SDK inspired by the Claude Agent SDK programming model.

Status: early (APIs may change), but the core runtime + tool loop are usable today.

This project exists for people who want the “agent runtime” experience (multi-turn sessions, tool calls, approvals,
skills/commands from `.claude/`, resumable logs) in a small, hackable Python codebase.

See `README.zh_cn.md` for a Chinese overview.

## What you get

- **A minimal agent runtime**: `run()` / streaming `query()` / CAS-style `query_messages()`.
- **A persistent session model**: durable `session_id`, `events.jsonl`, `resume=<session_id>`.
- **A real tool loop**: model requests tools → permission gate → tool execution → tool results → model continues.
- **Human-friendly console output** by default (debug mode available).
- **`.claude` compatibility**: project memory, slash commands, and skills on disk.
- **OpenAI + OpenAI-compatible providers** (the examples use a real OpenAI-compatible backend by default).

## Quickstart (uv)

Prereqs: Python 3.11+ and `uv`.

Install into a new project:

```bash
mkdir oas_test && cd oas_test
uv init
uv add openagentic-sdk
export RIGHTCODE_API_KEY="..."  # required
export RIGHTCODE_BASE_URL="https://www.right.codes/codex/v1"  # optional
export RIGHTCODE_MODEL="gpt-5.2"  # optional
export RIGHTCODE_TIMEOUT_S="120"  # optional
uv run oa chat
```

Windows (PowerShell):

```powershell
mkdir oas_test
cd oas_test
uv init
uv add openagentic-sdk
$env:RIGHTCODE_API_KEY="..."  # required
$env:RIGHTCODE_BASE_URL="https://www.right.codes/codex/v1"  # optional
$env:RIGHTCODE_MODEL="gpt-5.2"  # optional
$env:RIGHTCODE_TIMEOUT_S="120"  # optional
uv run oa chat
```

## Quickstart (local)

Prereqs: Python 3.11+.

Install (optional, for editable dev):

`pip install -e .`

Set env (examples + CLI default to RIGHTCODE):

- `RIGHTCODE_API_KEY` (required)
- `RIGHTCODE_BASE_URL` (optional, default `https://www.right.codes/codex/v1`)
- `RIGHTCODE_MODEL` (optional, default `gpt-5.2`)
- `RIGHTCODE_TIMEOUT_S` (optional, default `120`)
- `TAVILY_API_KEY` (optional; enables Tavily-backed `WebSearch` and `WebFetch` fallback extraction)
- `OPENAGENTIC_WEBFETCH_TAVILY_EXTRACT` (optional; default `1` when `TAVILY_API_KEY` is set)
- `OPENAGENTIC_WEBFETCH_TAVILY_EXTRACT_DEPTH` (optional; `basic` or `advanced`, default `advanced`)

Run unit tests:

`python3 -m unittest -q`

Run examples:

- `python3 example/01_run_basic.py`
- See `example/README.md` for the full list and required env vars.

## `oa` CLI

Install (editable):

`pip install -e .`

If `oa` isn't found after installation on Windows, add the scripts directory printed by pip to `PATH` (or run `python -m openagentic_cli chat`).

Install via `uv` (recommended):

```bash
uv add openagentic-sdk
uv run oa --help
uv run oa chat
```

Optional (recommended): install ripgrep (`rg`) so the agent can search your repo quickly when using shell tools.

- Windows (PowerShell): `winget install BurntSushi.ripgrep.MSVC`
- WSL/Ubuntu: `sudo apt-get update && sudo apt-get install -y ripgrep`

Commands:

 - `oa chat` (multi-turn REPL; `/help` for commands; multi-line paste is submitted as one turn on TTYs, or use `/paste` ... `/end`)
- `oa run "prompt"` (`--json`, `--no-stream`)
- `oa resume <session_id>` (alias of `oa chat --resume <session_id>`)
- `oa logs <session_id>` (summarize `events.jsonl`)

Server + integrations:

- `oa serve --port 4096` (local HTTP server)
- `oa --port 4096` (alias of `oa serve --port 4096` for OpenCode VSCode parity)
- `oa acp` (ACP stdio server)
- `oa github install` (generate a GitHub Actions workflow)
- `oa github run` (GitHub Actions runner)

Sessions are stored under `~/.openagentic-sdk` by default (override with `OPENAGENTIC_SDK_HOME`).

For user-facing OpenCode parity docs, see:

- `docs/guides/opencode-parity-v2/README.md`

## Publishing

See `docs/publishing.md`.

## Usage

Streaming:

```py
import asyncio
from openagentic_sdk import OpenAgenticOptions, query
from openagentic_sdk.providers import OpenAIProvider
from openagentic_sdk.permissions import PermissionGate


async def main() -> None:
    options = OpenAgenticOptions(
        provider=OpenAIProvider(),
        model="gpt-4.1-mini",
        api_key="...",  # OpenAI API key
        permission_gate=PermissionGate(permission_mode="prompt", interactive=True),
        setting_sources=["project"],
    )

    async for event in query(prompt="Find TODOs in this repo", options=options):
        print(event.type)


asyncio.run(main())
```

One-shot:

```py
import asyncio
from openagentic_sdk import OpenAgenticOptions, run
from openagentic_sdk.providers import OpenAIProvider
from openagentic_sdk.permissions import PermissionGate


async def main() -> None:
    options = OpenAgenticOptions(
        provider=OpenAIProvider(),
        model="gpt-4.1-mini",
        api_key="...",
        permission_gate=PermissionGate(permission_mode="callback", approver=lambda *_: True),
    )
    result = await run(prompt="Explain this project", options=options)
    print(result.final_text)


asyncio.run(main())
```

OpenAI-compatible backend (the examples default to RIGHTCODE):

```py
from openagentic_sdk import OpenAgenticOptions, run
from openagentic_sdk.providers.openai_compatible import OpenAICompatibleProvider
from openagentic_sdk.permissions import PermissionGate

options = OpenAgenticOptions(
    provider=OpenAICompatibleProvider(base_url="https://www.right.codes/codex/v1"),
    model="gpt-5.2",
    api_key="...",  # RIGHTCODE_API_KEY
    cwd=".",
    permission_gate=PermissionGate(permission_mode="prompt", interactive=True),
    setting_sources=["project"],
)
```

## Built-in tools

Default registry includes:

- `Read`, `Write`, `Edit`
- `Glob`, `Grep`
- `Bash`
- `WebFetch` (direct HTTP(S); falls back to Tavily Extract for blocked/JS-shell pages when `TAVILY_API_KEY` is set)
- `WebSearch` (Tavily; requires `TAVILY_API_KEY`)
- `TodoWrite`
- `SlashCommand` (loads `.claude/commands/<name>.md`)
- `Skill` (load a Skill by `name`; available skills are listed in the tool description)

For OpenAI-compatible providers, tool schemas include long-form “how to use this tool” descriptions (opencode-style)
to make the model follow rules more reliably.

## `.claude` compatibility

When `setting_sources=["project"]`, the SDK can index:

- `CLAUDE.md` or `.claude/CLAUDE.md` (memory)
- `.claude/commands/*.md`

Skills are discovered from:

- Project (compat): `.claude/{skill,skills}/**/SKILL.md`
- Global: `~/.openagentic-sdk/{skill,skills}/**/SKILL.md` (override with `OPENAGENTIC_SDK_HOME`)

When `setting_sources=["project"]`, `query()` prepends a `system` message with project memory + commands index (skills are exposed via the `Skill` tool description).

## Console output (human-first)

Examples use `openagentic_sdk.console.ConsoleRenderer`, which:

- Prints assistant text by default (human-friendly).
- In debug mode (`--debug` or `OPENAGENTIC_SDK_CONSOLE_DEBUG=1`), prints tool/hook/result summaries.

Try the interactive CLI chat example:

- `python3 example/45_cli_chat.py`

## Event compatibility

- `events.jsonl` is forward-compatible for added fields: deserialization ignores unknown keys on known event `type`s.
- Unknown event `type`s raise `openagentic_sdk.errors.UnknownEventTypeError`.



## The OpenAgentic SDK family

This Kotlin repo is part of a small “SDK family” that shares the same overall philosophy (traceable sessions/events + safe tools + deterministic gates), but targets different runtimes and product surfaces.

### 1) `openagentic-sdk` (Python, the origin)

- Repo: `https://github.com/lemonhall/openagentic-sdk`
- The earliest project in the family, and the **most battle-tested test suite** (reported ~369 tests).
- The most complete tool set, plus CLI utilities.
- Includes a TUI dashboard for observing sessions/traces.

### 2) `openagentic-sdk-ts` (TypeScript, sandbox-first)

- Repo: `https://github.com/lemonhall/openagentic-sdk-ts`
- Derived from the Python lineage, with a strong focus on a **complete sandbox system**.
- Provides a **browser sandbox**; designed to be extremely safe in Linux and browser environments.

Side project built on top of the TS stack:

- `WebMCP_Sidecar`: `https://github.com/lemonhall/WebMCP_Sidecar`
- A full-featured **browser sidebar AI assistant** with WebMCP support.

### 3) `openagentic-sdk-gdscript` (Godot 4.6, the most complex)

- Repo: `https://github.com/lemonhall/openagentic-sdk-gdscript`
- A Godot 4.6 SDK that ships multiple demos, including a **VR Office** and a 2D demo.
- Contains a full-featured **IRC client SDK** for GDScript.
- Implements an IRC-based RPC protocol and supports a multi-machine architecture (OpenClaw-like).

### 4) `openagentic-sdk-kotlin` (Android-oriented)

- Repo: `https://github.com/lemonhall/openagentic-sdk-kotlin`
- A full Kotlin SDK architecture intended as a reusable core for Android apps.

### Planned siblings (to make ~6)

- Swift (Apple platforms)
- Rust (systems + embedded/CLI)

The exact feature distribution may evolve, but the goal is consistent: **safe agent runtimes with strong, traceable tests**.
