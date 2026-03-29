# v60 Index

## Vision

v60 是对 v57 Jaeger tracing 链路和 v58/v59 Jaeger UI 能力的一次基础设施收口：

- 不是继续扩展 Jaeger 功能；
- 不是继续改聊天或 actor runtime；
- 而是把 Jaeger 的访问方式从“靠手工 port-forward 临时打开”升级为“集群起来后固定地址直接可达”。

这一版只解决一个问题：

- `http://127.0.0.1:16686` 必须成为真实、稳定、默认的 Jaeger 入口。

## Milestones

- **M1: Jaeger Service 暴露语义对齐**
  - Plan: `docs/plan/v60-jaeger-loadbalancer-exposure.md`
  - PRD: `docs/prd/PRD-0060-jaeger-loadbalancer-exposure-v60.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_k3d_jaeger_exposure`
    - `wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56 get svc jaeger-query -o jsonpath=\"{.spec.type}\""'`
  - Status: planned

- **M2: k3d 固定 16686 暴露与重建边界收口**
  - Plan: `docs/plan/v60-jaeger-loadbalancer-exposure.md`
  - PRD: `docs/prd/PRD-0060-jaeger-loadbalancer-exposure-v60.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_k3d_jaeger_exposure tests.test_cli_k3d_port_forward tests.test_k3d_harness_state_paths`
    - `curl.exe http://127.0.0.1:16686/`
  - Status: planned

- **M3: 手工测试与经验包文档收口**
  - Plan: `docs/plan/v60-jaeger-loadbalancer-exposure.md`
  - PRD: `docs/prd/PRD-0060-jaeger-loadbalancer-exposure-v60.md`
  - DoD（命令证据）：
    - 文档审阅通过
    - 手工测试指南不再把 Jaeger `port-forward` 作为默认路径
  - Status: planned

## Plan Index

- `docs/plan/v60-jaeger-loadbalancer-exposure.md`

## Traceability Matrix

- REQ-0060-001 → `docs/plan/v60-jaeger-loadbalancer-exposure.md` → `tests.test_k3d_jaeger_exposure` + `kubectl get svc jaeger-query` → pending
- REQ-0060-002 → `docs/plan/v60-jaeger-loadbalancer-exposure.md` → `tests.test_k3d_jaeger_exposure` + cluster config diff review → pending
- REQ-0060-003 → `docs/plan/v60-jaeger-loadbalancer-exposure.md` → `curl.exe http://127.0.0.1:16686/` + manual workflow review → pending
- REQ-0060-004 → `docs/plan/v60-jaeger-loadbalancer-exposure.md` → docs review + recreate workflow verification → pending
- REQ-0060-005 → `docs/plan/v60-jaeger-loadbalancer-exposure.md` → `tests.test_k3d_jaeger_exposure` + real cluster regression → pending
- REQ-0060-006 → `docs/plan/v60-jaeger-loadbalancer-exposure.md` → doc review + command surface review → pending

## ECN

- None
