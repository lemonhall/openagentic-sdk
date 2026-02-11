from __future__ import annotations

from ...mcp.client import StdioMcpClient
from ...mcp.remote_client import RemoteMcpClient
from ...mcp.sdk import McpSdkServerConfig, wrap_sdk_server_tools
from ...mcp.wrappers import (
    wrap_http_mcp_prompts,
    wrap_http_mcp_resources,
    wrap_http_mcp_tools,
    wrap_stdio_mcp_prompts,
    wrap_stdio_mcp_resources,
    wrap_stdio_mcp_tools,
)
from ...options import OpenAgenticOptions


async def register_mcp_surface(options: OpenAgenticOptions) -> tuple[list[StdioMcpClient], list[RemoteMcpClient]]:
    mcp_clients: list[StdioMcpClient] = []
    remote_mcp_clients: list[RemoteMcpClient] = []

    # MCP (parity): register SDK and local-stdio MCP tools.
    if not options.mcp_servers:
        return mcp_clients, remote_mcp_clients

    for server_key, cfg in options.mcp_servers.items():
        if isinstance(cfg, McpSdkServerConfig) and cfg.type == "sdk":
            for wrapper in wrap_sdk_server_tools(server_key, cfg):
                try:
                    options.tools.get(wrapper.name)
                except KeyError:
                    options.tools.register(wrapper)
            continue

        if isinstance(cfg, dict) and cfg.get("type") == "local":
            cmd = cfg.get("command")
            env = cfg.get("environment") if isinstance(cfg.get("environment"), dict) else None
            if not isinstance(cmd, list) or not all(isinstance(x, str) and x for x in cmd):
                continue

            client = StdioMcpClient(command=list(cmd), environment=env, cwd=options.cwd)
            try:
                await client.start()
                tools = await client.list_tools()
            except Exception:
                # Non-fatal: allow sessions to run even if an MCP server is down.
                try:
                    await client.close()
                except Exception:
                    pass
                continue

            for w in wrap_stdio_mcp_tools(str(server_key), client=client, tools=tools):
                try:
                    options.tools.get(w.name)
                except KeyError:
                    options.tools.register(w)

            # Prompts/resources are part of the MCP surface too.
            try:
                prompts = await client.list_prompts()
                for w in wrap_stdio_mcp_prompts(str(server_key), client=client, prompts=prompts):
                    try:
                        options.tools.get(w.name)
                    except KeyError:
                        options.tools.register(w)
            except Exception:
                pass

            try:
                resources = await client.list_resources()
                for w in wrap_stdio_mcp_resources(str(server_key), client=client, resources=resources):
                    try:
                        options.tools.get(w.name)
                    except KeyError:
                        options.tools.register(w)
            except Exception:
                pass

            mcp_clients.append(client)

        if isinstance(cfg, dict) and cfg.get("type") == "remote":
            url = cfg.get("url")
            if not isinstance(url, str) or not url:
                continue
            headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else None
            client2 = RemoteMcpClient(
                url=url,
                headers={str(k): str(v) for k, v in (headers or {}).items()},
                server_key=str(server_key),
            )
            try:
                tools2 = await client2.list_tools()
            except Exception:
                try:
                    await client2.close()
                except Exception:
                    pass
                continue

            for w in wrap_http_mcp_tools(str(server_key), client=client2, tools=tools2):
                try:
                    options.tools.get(w.name)
                except KeyError:
                    options.tools.register(w)

            try:
                for w in wrap_http_mcp_prompts(str(server_key), client=client2, prompts=await client2.list_prompts()):
                    try:
                        options.tools.get(w.name)
                    except KeyError:
                        options.tools.register(w)
            except Exception:
                pass

            try:
                for w in wrap_http_mcp_resources(str(server_key), client=client2, resources=await client2.list_resources()):
                    try:
                        options.tools.get(w.name)
                    except KeyError:
                        options.tools.register(w)
            except Exception:
                pass

            remote_mcp_clients.append(client2)

    return mcp_clients, remote_mcp_clients


async def close_mcp_clients(mcp_clients: list[StdioMcpClient], remote_mcp_clients: list[RemoteMcpClient]) -> None:
    for c in mcp_clients:
        try:
            await c.close()
        except Exception:  # noqa: BLE001
            pass
    for c in remote_mcp_clients:
        try:
            await c.close()
        except Exception:  # noqa: BLE001
            pass
