# Windows CLI e2e（Windows 原生）

这是一套 Windows 11 专用的 `openagentic_cli` 交互式 E2E（**独立套件**），用于在 Windows 原生环境下端到端验证：

- CLI 的交互命令（`/help`、`/exit`、`/paste` 等）
- 与真实 Provider 的真实网络调用（凭据来自仓库根目录 `.env` 或当前环境变量）

当前默认驱动方式为 **ConPTY（Pseudo Console / 真 TTY）**（见 `e2e_cli_win_tests/_conpty.py`），用于更真实地覆盖交互式 CLI（光标定位、回显、VT 序列、粘贴模式等）。

如遇 ConPTY 相关问题，可临时切回 **stdio pipes**（见 `e2e_cli_win_tests/_pipes.py`）做对照排查。

## 运行方式

在 Windows 11 的 PowerShell 里：

```powershell
python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v
```

## 环境变量

- `RIGHTCODE_API_KEY`（或 `OPENAI_API_KEY`）
- 可选：`RIGHTCODE_BASE_URL` / `RIGHTCODE_MODEL`

说明：`openagentic_cli` 自身不会读取 `.env`，这里的测试 harness 会 best-effort 加载仓库根目录 `.env`。
