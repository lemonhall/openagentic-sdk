# PRD-0023 — Real-Network E2E (CLI Subcommands v23)（真实网络 E2E：CLI 子命令覆盖 v23）

## Vision

在 v21 覆盖 `oa chat`（真 TTY/PTY）基础上，扩展 `openagentic_cli` 的子命令 E2E 覆盖：

- 覆盖非 REPL 子命令的真实链路（CLI → SDK → Provider / Sessions / Share / Auth）；
- 保持强隔离与可回归（不污染用户目录、不读取用户全局 opencode 配置、断言以落盘/确定性输出为主）；
- 仍然保持套件独立，不影响 `e2e_tests/`。

## Non-Goals

- 不覆盖 `oa serve` / `oa acp` 的长驻服务型场景（可另起版本，专测端口/生命周期/并发）。
- 不测试 MCP OAuth（涉及浏览器回调、端口占用与外部依赖；暂不纳入 v23）。

## Requirements

### REQ-0023-001 — `oa run --json` emits machine-readable JSON（真实网络）

新增 E2E：调用 `oa run --json "<prompt>"`：
- exit code = 0
- stdout 为 JSON，且包含字段：`final_text`、`session_id`、`stop_reason`
- `session_id` 对应的 `events.jsonl` 落盘存在（以 `OPENAGENTIC_SDK_HOME` 为根）

### REQ-0023-002 — `oa run --no-stream` emits final text and persists session（真实网络）

新增 E2E：调用 `oa run --no-stream "<prompt>"`：
- exit code = 0
- stdout 包含期望 token（确定性字符串）
- `events.jsonl` 存在，且包含最终文本（不要求包含 streaming delta）

### REQ-0023-003 — `oa share` / `oa shared` / `oa unshare` roundtrip works (local/offline)（落盘互操作）

新增 E2E：在生成 session 后：
- `oa share <session_id>` 输出 `share_id`
- `oa shared <share_id>` 输出非空 payload
- `oa unshare <share_id>` 后再次 `oa shared <share_id>` 应失败或返回明确错误（以 exit code/文本判定）

> 注：share 在本项目默认是 offline/local，但它属于“CLI 实用性链路”，仍需要 E2E 覆盖。

### REQ-0023-004 — `oa auth set/list/remove` works and is isolated (no secret leakage)（落盘与隔离）

新增 E2E：
- `oa auth set <provider_id> --key <fake>` → 输出包含 “Stored auth”
- `oa auth list` → 包含 `<provider_id>`
- `oa auth remove <provider_id>` → 输出包含 “Removed auth”
- 再次 `oa auth list` → 不包含 `<provider_id>`

约束：
- key 必须是测试生成的 fake key；不得使用真实 key；不得把 key 输出到日志/断言文本中。
- `auth.json` 必须落盘在临时 `OPENAGENTIC_SDK_HOME` 下（强隔离）。

## Acceptance (DoD)

必须全部满足：

1) WSL2/Linux/macOS 下：
   - `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v` exit code=0
2) v23 新增用例覆盖 REQ-0023-001..004，并在 v23 计划中写出可复现 Evidence。

