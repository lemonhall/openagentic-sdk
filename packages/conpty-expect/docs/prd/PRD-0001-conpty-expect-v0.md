# PRD-0001 — conpty-expect v0（Windows-first）

## 背景

在 Windows 下测试交互式 CLI/TUI（尤其是 REPL、粘贴模式、VT 序列、光标控制）时，纯 `stdio pipes` 很容易与真实终端行为偏离。ConPTY（Pseudo Console）提供了“真 TTY”语义，但缺少一个可复用、可发布、接近 `pexpect` 体验的测试框架。

本 PRD 目标是在 `openagentic-sdk` 仓库内以子项目形式孵化一个 pip 包：`conpty-expect`。

## 目标（v0）

- 提供 Windows ConPTY 后端的 `spawn/expect` 能力（**Windows-first**）。
- 对外语义尽量兼容 `pexpect`：
  - `spawn(...) -> child`
  - `child.send()/sendline()`
  - `child.expect([pattern...]) -> index`
  - `child.before/after/match`
  - `TIMEOUT/EOF` sentinel
- 子项目自包含：
  - 自己的 `pyproject.toml`
  - 自己的 `docs/` 与 `tests/`
  - 不与主项目根目录 `docs/` 混用
- 测试生态一等公民：
  - `unittest` 与 `pytest` 都能写、都能跑

## 非目标（v0 不做）

- POSIX pty（Linux/macOS）实现（只保留 API 形状，后续版本再补）。
- 完整覆盖所有 VT 查询/终端协商（先提供最小子集，避免 CLI 卡住）。
- 追求最高性能（稳定优先）。

## 验收标准（DoD）

- 在 Windows 11 上：
  - `python -m unittest discover -s packages/conpty-expect/tests -p "ce_test_*.py" -v` 通过
  - `pytest -q packages/conpty-expect/tests` 通过（安装 dev 依赖后）
- `expect` 具备：
  - 多 pattern 列表匹配并返回 index
  - 正确维护 `before/after/match`
  - `TIMEOUT`/`EOF` sentinel 可用
- 调试能力：
  - 超时/EOF 异常包含尾部输出（tail）
  - 可选输出 debug timeline（环境变量开关）

## 风险

- Windows ConPTY 读写存在边界条件与偶发性：优先用“保守稳定”的实现策略，必要时回退对照验证。

