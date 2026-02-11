# PRD-0013 — Real-Network E2E (Sessions Transcript Redaction)（真实网络 E2E：会话落盘与转录脱敏）

## Vision

用真实网络 E2E 验证会话落盘的两条通道语义稳定：
- `events.jsonl` 作为审计日志：包含 tool 结果（用于回放/调试）。
- `transcript.jsonl` 作为 UI 转录：不包含 tool inputs/outputs，避免意外泄露。

## Non-Goals

- 不测试 Gateway/MCP。
- 不做大输出；用短 token 触发即可。

## Requirements

### REQ-0013-001 — transcript excludes tool output but events include it（真实网络）

当工具读取到包含 token 的文件时：
- `events.jsonl` 必须包含该 token（在 tool.result 输出中）；
- `transcript.jsonl` 必须不包含该 token（只含 user/assistant message 文本）。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0013-001

