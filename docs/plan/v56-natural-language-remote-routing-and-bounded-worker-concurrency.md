# v56 M3 — 自然语言 remote subagent 路由与有界 worker 并发

## Goal

让 cluster-hosted 主会话不再只靠 `TASK_A` / `TASK_B` 这类固定触发词，而是能感知两个具名 remote subagent，并在自然语言场景下做到：

- 用户显式点名时，准确派发到对应 remote subagent；
- 用户不点名时，主模型根据 agent description / prompt 自动路由；
- 默认走串行编排，例如先研究、再写作；
- 对可拆分的原子任务允许 fan-out 并发；
- 同一 remote worker 节点默认最多同时执行 3 个任务，超限时排队等待。

## PRD Trace

- REQ-0056-011
- REQ-0056-012
- REQ-0056-013
- REQ-0056-014

## Scope

做：

- 修正 `Task` 工具提示，使模型真正看到具名 agent 清单
- 为 worker 增加默认 `max_concurrent_tasks=3` 的有界并发 contract
- 在 smoke provider / k3d chat smoke 中引入两个具名 remote subagent：
  - `research`
  - `writer`
- 提供一条串行编排 smoke：
  - 先 `research`
  - 再 `writer`
- 提供一条原子 fan-out smoke：
  - 主会话拆出多个研究子任务
  - 并发派发给同类研究 subagent
  - 主会话自行汇总

不做：

- 不做跨节点 `group` 负载均衡
- 不做 worker group 的最低负载挑选
- 不做真正的调度器 / broker / queue service
- 不做动态扩缩容或多副本 worker shared queue

## Design Notes

- M3 不是引入一个“特殊 orchestration engine”，而是继续沿用现有 `Task` 语义，只是把主模型对 remote agents 的可见性补全。
- “自然语言自动路由”本质上依赖模型提示质量；因此需要同时落地：
  - agent 列表注入到 `Task` 工具提示
  - smoke provider 对应的 deterministic 路由测试桩
- worker 并发上限首版放在 `AgentWorkerDefinition` 里，理由是它属于 worker 侧资源能力，而不是 executor 拓扑信息。
- 超出上限时阻塞等待即可满足“队列化”语义；M3 不额外引入显式队列对象或单独调度进程。

## Acceptance (DoD)

必须全部满足：

1. 单元/集成：
   - `python -m unittest -q tests.test_openai_tool_schemas tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_http_transport tests.test_remote_chat_bridge`
2. WSL2/k3d smoke：
   - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_*.py\" -v"'`
3. 反作弊条款：
   - 不允许只在 smoke provider 里硬编码“自然语言 -> agent 名字”，却不把 agent 清单注入真实 `Task` 提示
   - 不允许 worker 只是“理论上可并发”，却没有任何并发上限或等待 contract
   - 不允许把第 4 个任务直接默默并发执行而不受上限控制

## Files

- `docs/prd/PRD-0056-k3s-distributed-readonly-subagents-v56.md`
- `docs/plan/v56-index.md`
- `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md`
- `openagentic_sdk/options.py`
- `openagentic_cli/config.py`
- `openagentic_sdk/tools/openai.py`
- `openagentic_sdk/tool_prompts/task.txt`
- `openagentic_sdk/subagents/remote_http.py`
- `e2e_k3d_tests/_smoke_provider.py`
- `e2e_k3d_tests/e2e_remote_chat_basic.py`
- `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py`
- `tests/test_openai_tool_schemas.py`
- `tests/test_agent_config_mapping.py`
- `tests/test_remote_http_transport.py`

## Test Contract

### Contract A — `Task` 工具提示必须包含具名 remote agents

`tests.test_openai_tool_schemas` 至少覆盖：

- `Task` description 不再残留 `subagent_type`
- `Task` description 明确要求传 `agent`
- `Task` description 中包含配置里的 agent 名字、description、tools、node_name

### Contract B — worker 并发上限必须真实生效

`tests.test_remote_http_transport` 至少覆盖：

- 默认 `max_concurrent_tasks == 3`
- 同一 worker 的第 4 个任务不会立即进入执行态
- 前 3 个任务释放后，第 4 个任务继续运行并返回结果

### Contract C — chat host 自然语言串行编排

`e2e_remote_chat_basic.py` 至少覆盖：

1. 用户发一个自然语言请求，要求先研究、再写作
2. 主会话先派发 `research`
3. 收到研究结果后，再派发 `writer`
4. 最终结果回到主会话
5. `tool.result` 至少保留每次 remote 派发的 node / revision / execution id

### Contract D — chat host 原子 fan-out 并发研究

`e2e_remote_chat_sync_after_session.py` 或新增 smoke 至少覆盖：

1. 主会话把一个研究请求拆成多个子方向
2. 并发派发多个 `research` 子任务
3. 主会话在本地汇总研究结果
4. 同时不突破 worker 并发上限 contract

## Steps

1. 文档回填
   - 扩展 PRD，补充 M3 requirements
   - 更新 `v56-index`，加入 M3 milestone

2. TDD Red：`Task` 提示链
   - 先写失败测试，证明 agent 清单没有进入 `Task` 提示或字段名不一致

3. TDD Green：agent 列表注入
   - 在 schema 构造阶段注入具名 agent 清单
   - 修正 `Task` prompt 中过时字段名

4. TDD Red：worker 并发 contract
   - 先写失败测试，证明第 4 个任务当前不会等待

5. TDD Green：bounded concurrency
   - 给 remote worker server 增加 `max_concurrent_tasks`
   - 默认值设为 `3`
   - 超限时阻塞等待

6. TDD Red：smoke provider 自然语言路由
   - 先写失败 smoke / unit，证明固定 `TASK_A` / `TASK_B` 无法覆盖 M3

7. TDD Green：串行 + fan-out
   - 把 smoke host provider 升级为：
     - `research` / `writer` 两个具名 remote agents
     - 自然语言串行 research -> writer
     - 原子 fan-out 研究并汇总

8. 验证与回填
   - 跑单测、lint、k3d smoke
   - 回填 `v56-index` Evidence 与 Status

## Evidence

- Date: 2026-03-28
- Env: Windows 11 + PowerShell 7.x
- Verification:
  - `python -m unittest -q tests.test_openai_tool_schemas tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport tests.test_remote_chat_bridge tests.test_remote_git_sync_policy tests.test_remote_session_meta`
  - `ruff check openagentic_cli/config.py openagentic_sdk/options.py openagentic_sdk/tools/openai.py openagentic_sdk/runtime_core/query_loop_steps/tool_schemas.py openagentic_sdk/subagents/remote_http.py e2e_k3d_tests/_smoke_provider.py e2e_k3d_tests/e2e_remote_chat_basic.py e2e_k3d_tests/e2e_remote_chat_sync_after_session.py e2e_k3d_tests/e2e_remote_chat_fanout.py tests/test_openai_tool_schemas.py tests/test_agent_config_mapping.py tests/test_remote_http_transport.py tests/test_remote_chat_bridge.py --config ruff.toml`
  - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_*.py\" -v"'`
- Result:
  - 本地定向单元/集成测试通过
  - 定向 Ruff lint 通过
  - k3d chat smoke 通过，覆盖 greeting、串行 research -> writer、fan-out 并发研究、dirty sync 恢复
- Status: done
