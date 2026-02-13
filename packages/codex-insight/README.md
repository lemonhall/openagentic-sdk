# codex-insight

一个 Textual TUI：读取 Codex CLI 的 session 数据（SQLite + rollout JSONL），给出全局 Dashboard，并支持下钻到单条 session。

> 注：本目录是 `openagentic-sdk` 仓库里的一个独立子项目（类似 `packages/conpty-expect/`）。

## 快速开始（PowerShell）

```powershell
cd E:\development\openagentic-sdk
uv pip install -e packages/codex-insight[all]
codex-insight
```

默认会自动探测：
- Codex CLI 配置：`~/.codex/config.toml`
- Sessions JSONL：`~/.codex/sessions/**/*.jsonl`

如需启用 AI Review（按 `r` 生成 review），需要先把本仓库的核心 SDK 装进同一个虚拟环境：

```powershell
uv pip install -e .
```

如果你只想先跑纯浏览（无 AI / 无缓存 DB），也可只装最小依赖：

```powershell
uv pip install -e packages/codex-insight
codex-insight
```

## 配置

默认读取：`~/.codex-insight/config.toml`（Windows 同样用用户目录）。
