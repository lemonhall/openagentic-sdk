# conpty-expect

Windows-first（ConPTY）`spawn/expect` 测试框架，目标是提供尽量接近 `pexpect` 的语义，用于测试交互式 CLI/TUI（真 TTY）。

> v0：只实现 Windows ConPTY；对外 API 预留跨平台形状（未来可补 POSIX pty）。

## 安装（开发态）

在本仓库根目录（PowerShell）：

```powershell
uv pip install -e packages/conpty-expect
```

如果你还没在仓库根目录创建虚拟环境，先执行：`uv venv`
（或直接用下方的 `python -m unittest ...` 跑测试，不要求安装）。

（可选）安装开发依赖：

```powershell
uv pip install -e "packages/conpty-expect[dev]"
```

## 运行测试

unittest：

```powershell
python -m unittest discover -s packages/conpty-expect/tests -p "ce_test_unittest_*.py" -v
```

pytest（需安装 dev 依赖）：

```powershell
pytest -q packages/conpty-expect/tests
```

## 调试

- `CONPTY_EXPECT_DEBUG=1`：在超时异常中附加 debug timeline
- `CONPTY_EXPECT_DEBUG_PATH=...`：把 debug timeline 追加写入文件（UTF-8）
