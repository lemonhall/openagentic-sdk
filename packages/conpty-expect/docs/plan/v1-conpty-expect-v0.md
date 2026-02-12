# v1 — conpty-expect v0（Windows-first）

PRD：`packages/conpty-expect/docs/prd/PRD-0001-conpty-expect-v0.md`

## 里程碑

1) 子项目骨架（pyproject/src/tests/docs）
2) ConPTY spawn/expect 核心（pexpect-like）
3) unittest + pytest 双套件通过
4) 调试能力（timeline + tail）

## 具体步骤（可验证）

### Step 1：安装（可编辑）

```powershell
uv pip install -e packages/conpty-expect
```

### Step 2：unittest 验证

```powershell
python -m unittest discover -s packages/conpty-expect/tests -p "ce_test_unittest_*.py" -v
```

### Step 3：pytest 验证（dev）

```powershell
uv pip install -e "packages/conpty-expect[dev]"
pytest -q packages/conpty-expect/tests
```

## 风险与对策

- ConPTY 输出读取/关闭的 race：EOF 前做短暂 drain（不延长整体 timeout），避免漏读尾部输出。
- ANSI 控制序列导致 match/consume 索引错位：strip 时返回 index map，把匹配跨度映射回原始缓冲区再消费。
- 多字节编码跨 chunk：使用增量 decoder，避免 `decode(errors="replace")` 造成偶发替换字符。
- 时间回拨导致 timeout 抖动：统一改用 `time.monotonic()`。
