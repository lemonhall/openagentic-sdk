# CLI e2e (online, PTY)

这是一套**独立**的 `openagentic_cli` E2E 测试集：用 **真 TTY/pty** 驱动 REPL 交互，并通过真实网络调用 Provider（读取仓库根目录 `.env`）。

它不会被 `e2e_tests/` 或默认的 `python -m unittest -q` 自动运行。

## 运行方式

### 推荐：在 WSL2 / Linux / macOS（需要 POSIX pty）

```bash
python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v
```

### Windows 原生

Windows 下没有 stdlib 的 POSIX pty，本套件会自动 skip；请用 WSL2 跑。

## 环境变量（最少）

- `RIGHTCODE_API_KEY`（或 `OPENAI_API_KEY`）
- 可选：`RIGHTCODE_BASE_URL` / `RIGHTCODE_MODEL`

说明：`openagentic_cli` 自身不会读取 `.env`，这里的测试 harness 会 best-effort 加载仓库根目录 `.env`。

