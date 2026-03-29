# v61 Index

## Vision

v61 只做一件事：

- 把 `real-model` 的冷启动慢点从“Pod 启动时本地 pip install”彻底收口为“本地预烘焙 runtime image”。

这一版不是功能扩张，也不是 actor / tracing 改造，而是把一个已经明确暴露出来的运行时成本点做掉：

- 用户继续只记：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
- 但这条链在 `wsl --shutdown` 之后的首次恢复，不应该再被容器内依赖安装拖慢。

## Milestones

- **M1: Runtime Image Contract**
  - Plan: `docs/plan/v61-real-runtime-prebaked-image.md`
  - PRD: `docs/prd/PRD-0061-real-runtime-prebaked-image-v61.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_apply_v56_real_cluster tests.test_k3d_real_runtime_image`
  - Status: todo

- **M2: Build / Preload / Apply Pipeline**
  - Plan: `docs/plan/v61-real-runtime-prebaked-image.md`
  - PRD: `docs/prd/PRD-0061-real-runtime-prebaked-image-v61.md`
  - DoD（命令证据）：
    - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && PYTHONPATH=/mnt/e/development/openagentic-sdk python3 scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.json --env-file .openagentic.remote.env --output-dir .openagentic-rendered --apply"'`
    - `wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-0 --timeout=180s && kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-1 --timeout=180s && kubectl -n openagentic-v56-real rollout status deployment/oa-cluster-chat-host --timeout=180s"'`
  - Status: todo

- **M3: WSL2 冷启动回归**
  - Plan: `docs/plan/v61-real-runtime-prebaked-image.md`
  - PRD: `docs/prd/PRD-0061-real-runtime-prebaked-image-v61.md`
  - DoD（命令证据）：
    - `wsl --shutdown`
    - `oa chat --k3d-real`
    - `curl.exe http://127.0.0.1:16686/api/services`
  - Status: todo

## Plan Index

- `docs/plan/v61-real-runtime-prebaked-image.md`

## Traceability Matrix

- REQ-0061-001 → `docs/plan/v61-real-runtime-prebaked-image.md` → `tests.test_k3d_real_runtime_image` → pending
- REQ-0061-002 → `docs/plan/v61-real-runtime-prebaked-image.md` → `tests.test_k3d_real_runtime_image` + manifest diff review → pending
- REQ-0061-003 → `docs/plan/v61-real-runtime-prebaked-image.md` → `tests.test_apply_v56_real_cluster` + apply/build/preload regression → pending
- REQ-0061-004 → `docs/plan/v61-real-runtime-prebaked-image.md` → `wsl --shutdown` + `oa chat --k3d-real` cold-start regression → pending
- REQ-0061-005 → `docs/plan/v61-real-runtime-prebaked-image.md` → missing-image failure path test + manual error review → pending
- REQ-0061-006 → `docs/plan/v61-real-runtime-prebaked-image.md` → scope review + smoke regression check → pending
- REQ-0061-007 → `docs/plan/v61-real-runtime-prebaked-image.md` → real rollout + Jaeger services verification → pending

## ECN

- None
