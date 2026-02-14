# v54 Plan — Opencode Tests Checklist Parity（源头测试清单：对齐与补测）

## Goal

以 `docs/research/opencode-tests-checklist.md` 为输入，按核心模块范围把 P0/P1 能力点在本仓库落成：

- 有测试证据（unit/offline-e2e/real-e2e 任一），或
- 明确 N/A（设计差异）并写清楚原因。

本轮聚焦：补齐 Tools（Read/Grep/Bash/List/custom-tools discovery）的缺口测试。

## PRD Trace

- REQ-0054-001
- REQ-0054-002
- REQ-0054-003
- REQ-0054-004
- REQ-0054-005
- REQ-0054-006

## Scope

做：

- 新增/补齐 `tests/` 下的单元测试，覆盖 Read/Grep/Bash/List/custom-tools discovery 的 P0/P1 边界
- 必要时对 `openagentic_sdk/custom_tools.py` 做最小调整，使其满足“优先级/覆盖”规格并可被测试锁定
- 更新 `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md`：把 v54 补齐的缺口从 ❌ 变为 ✅/△/N/A

不做：

- 不引入真实网络依赖（不跑 `e2e_tests/`）
- 不新增第三方依赖
- 不实现清单中已判定为 N/A 的特性（external_directory prompting / apply_patch / WebFetch attachments / PermissionNext / structured output 等）

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -q` exit code=0
2) `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md` 中 v54 列出的 P0 缺口全部消除（❌ → ✅/△/N/A）
3) 新增测试不读取真实密钥、不发真实网络请求

## Files（预期变更路径）

- `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md`
- `docs/plan/v54-index.md`
- `docs/plan/v54-opencode-tests-checklist-parity.md`
- `docs/prd/PRD-0054-opencode-tests-checklist-parity-v54.md`
- （新增）`tests/test_read_tool_edges.py`
- （新增）`tests/test_grep_tool_edges.py`
- （新增）`tests/test_bash_tool_edges.py`
- （新增）`tests/test_custom_tools_precedence_and_isolation.py`
- （可选新增）`tests/test_list_tool_unit.py`
- （如需最小修正）`openagentic_sdk/custom_tools.py`

## Evidence（填写为可复现证据）

- Date: 2026-02-14
- Windows：`python -m unittest -q` → exit code 0（Ran 369 tests；OK；skipped=2）

## Steps（Strict）

1) Doc Gate（先对齐口径）
   - 打开 `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md`
   - 把本轮要补的缺口条目列为 checklist（P0 先于 P1）

2) TDD Red：ReadTool edges
   - 新增 `tests/test_read_tool_edges.py`
   - 至少覆盖：image mode / `.fbs` 文本 / abs+traversal 拒绝 / `/mnt/data` 映射 / `max_bytes`
   - 运行：`python -m unittest tests.test_read_tool_edges -v`（预期先红）

3) TDD Green：实现（如需要）
   - 仅当测试暴露出行为缺陷且与既有设计冲突时，做最小修正
   - 运行到绿：`python -m unittest tests.test_read_tool_edges -v`

4) TDD Red：GrepTool edges
   - 新增 `tests/test_grep_tool_edges.py`
   - 至少覆盖：no-match / CRLF / context / case-insensitive / max_matches truncation
   - 运行：`python -m unittest tests.test_grep_tool_edges -v`（预期先红）

5) TDD Green：实现（如需要）
   - 运行到绿：`python -m unittest tests.test_grep_tool_edges -v`

6) TDD Red：BashTool edges
   - 新增 `tests/test_bash_tool_edges.py`
   - 至少覆盖：output_lines_truncated / truncation 落盘 full_output_file_path / Windows POSIX path normalize
   - 运行：`python -m unittest tests.test_bash_tool_edges -v`（预期先红）

7) TDD Green：实现（如需要）
   - 运行到绿：`python -m unittest tests.test_bash_tool_edges -v`

8) TDD Red：custom tools precedence + import isolation
   - 新增 `tests/test_custom_tools_precedence_and_isolation.py`
   - 先用 PRD 的规则把 precedence 写成断言（global < project root < .opencode；tool < tools；重名覆盖；import 失败隔离）
   - 运行：`python -m unittest tests.test_custom_tools_precedence_and_isolation -v`（预期先红）

9) TDD Green：修正 `discover_custom_tool_files`（必要时）
   - 若 precedence 无法满足：对 `openagentic_sdk/custom_tools.py` 做最小修改，使其输出顺序可被测试锁定
   - 运行到绿：`python -m unittest tests.test_custom_tools_precedence_and_isolation -v`

10) P1（可选）：ListTool unit-level 快速回归
   - 新增 `tests/test_list_tool_unit.py`（树输出/忽略 junk/limit 截断）
   - 运行：`python -m unittest tests.test_list_tool_unit -v`

11) Verify + 回写证据
   - 运行：`python -m unittest -q`
   - 更新：
     - `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md`（状态变更）
     - `docs/plan/v54-index.md`（M1 Status: done + Deltas）
     - `docs/plan/v54-opencode-tests-checklist-parity.md`（Evidence）
