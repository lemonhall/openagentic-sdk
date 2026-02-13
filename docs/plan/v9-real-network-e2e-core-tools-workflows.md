# v9 Plan — Real-Network E2E (Core Tools Workflows)（真实网络 E2E：核心工具用户流程）

## Goal

新增 4 个真实网络 E2E，用“文件系统/产物断言”硬化验证，覆盖核心工具组合流程。

## PRD Trace

- REQ-0009-001
- REQ-0009-002
- REQ-0009-003
- REQ-0009-004

## Scope

做：
- 新增 4 个 `e2e_tests/e2e_*.py`
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做高成本长流程

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0009-001..004

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Env: Windows + PowerShell, Python 3.13, real-network provider via `e2e_tests/_harness.py` (dotenv supported)
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 24 tests in 156.163s`
  - `OK`

Notes:
- 为降低真实网络 LLM 行为波动，`Edit/NotebookEdit/Glob+Grep` 的 E2E 使用 `HookEngine.after_model_call` 做一次性 tool_calls 注入，确保 runtime_core 的 tool plumbing 必走、且以磁盘产物/tool.result 做硬断言。
- 在实现过程中发现 `Glob/Grep` 对 `root="."` 的相对路径解析不应依赖进程工作目录，已修正为相对 `ToolContext.cwd` 解析，避免真实会话与测试环境偏差。

## Steps（Strict）

1) Red：写 4 个 E2E 测试（同时写硬断言：文件内容/JSON/落盘产物）
2) Green：必要时微调 prompt 与 allowed_tools，降低波动
3) Verify：跑 DoD 命令并写回 Evidence
