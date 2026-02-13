# PRD-0044 — Windows CLI ConPTY Special Keys Matrix E2E (v44)（Windows 11：特殊键序列不污染输入回归扩容）

## Vision

把“特殊键/功能键序列污染输入”这个经典终端坑，继续做成 `openagentic_cli chat` 在 Windows ConPTY（真 TTY）下可守门的 E2E 回归：

- 常见 VT 序列（CSI/SS3，如方向键、Home/End、Insert/Delete、PgUp/PgDn、F1-F4）不会以字面 ESC 序列进入 `user.message.text`；
- 断言锚定 `events.jsonl`，避免依赖屏幕回显。

## Non-Goals

- 不在 v44 实现完整 line editor（方向键编辑/光标移动等），只守住“不污染输入/不落盘控制序列”。

## Requirements

### REQ-0044-001 — Special keys matrix does not leak ESC sequences into events.jsonl (ConPTY)

在 ConPTY 真 TTY 下，向输入流注入一组常见 VT 特殊键序列：

- CSI：`ESC[A`/`ESC[B`/`ESC[C`/`ESC[D`、`ESC[H`/`ESC[F`、`ESC[2~`、`ESC[3~`、`ESC[5~`、`ESC[6~`、`ESC[15~`（代表典型特殊键集合）
- SS3：`ESCOP`/`ESCOQ`/`ESCOR`/`ESCOS`（F1-F4）

验收：

- `events.jsonl` 的 `user.message.text` 不包含 `\x1b`（ESC）；
- 最终落盘文本与预期一致（特殊键序列应被忽略/消毒，不改变其余文本）。

### REQ-0044-002 — Suite remains isolated and opt-in

- 用例落在 `e2e_cli_win_tests/`，保持 opt-in；
- 运行命令：
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`

## Acceptance (DoD)

必须全部满足：

1) Windows 11 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0044-001..002 均有可追溯落地（Req → Plan → Tests → Evidence）。

