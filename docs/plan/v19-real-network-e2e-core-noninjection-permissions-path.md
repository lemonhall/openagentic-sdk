# v19 Plan — Real-Network E2E (Core Non-Injection + Permissions + Path Semantics)（真实网络 E2E：核心非注入 + 权限 + 路径语义）

## Goal

把核心真实网络 E2E 再推进一档：
- 更长的非注入工作流（Skill→多工具链→落盘）；
- acceptEdits/prompt 的权限语义硬回归；
- 纠偏并回归“相对路径以 cwd 为准、同时受 project_dir 约束”的路径语义；
- Windows 下未知 POSIX 绝对路径必须拒绝（避免误映射）。

## PRD Trace

- REQ-0019-001
- REQ-0019-002
- REQ-0019-003
- REQ-0019-004
- REQ-0019-005

## Scope

做：
- 新增 5 个真实网络 E2E
- 若发现实现与口径不一致，做最小修复（仅 tools/path 相关）
- full e2e 作为证据

不做：
- 不引入第三方依赖
- 不做 MCP / Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0019-001..005

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 57 tests in ~824s）

## Steps（Strict）

1) Red：先写 E2E（断言先行）
2) Green：最小修复 tools/path 语义
3) Verify：跑 full 并写回 Evidence
4) Delta：在 v19-index 填“愿景 vs 现实”
