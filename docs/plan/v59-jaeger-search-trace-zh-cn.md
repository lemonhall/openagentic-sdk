# v59 Plan — Jaeger Search / Trace 中文化与页面收口

## Goal

在不改入口、不改协议、不改 tracing / transcript 基础语义的前提下，把当前 Jaeger 中最常用的 `Search` 与 `Trace` 两个页面做成“中文可读、主题安全、便于继续调试”的状态，并把已经踩出来的构建 / packaging / k3d 导入经验沉淀成仓库内经验包。

## PRD Trace

- REQ-0059-001
- REQ-0059-002
- REQ-0059-003
- REQ-0059-004
- REQ-0059-005
- REQ-0059-006
- REQ-0059-007

## Scope

做：

- 给 `Search` 页面补简体中文 UI 文案
- 给 `Trace` 页面补简体中文 UI 文案
- 把 v58 transcript panel 的文案也一起纳入中文化范围
- 收掉 Search / Trace / transcript panel 中残余的颜色与对比度问题
- 保持深色 / 亮色主题都可读
- 增加中文化 / 主题安全静态资产测试
- 把 Jaeger UI 的 build / runtime packaging / k3d 导入经验写成文档

不做：

- 不做整个 Jaeger 的全量国际化
- 不做 `Compare` / `System Architecture` / `Monitor` 页面全文翻译
- 不改 `oa.*` tracing 字段
- 不改 transcript API
- 不改 session store 与 `events.jsonl`
- 不新增新的 CLI 入口或新的 Jaeger URL

## Recommended Architecture

### 1. 中文化边界

- 这一版不引入通用 i18n 框架，而是在 vendored Jaeger UI 源码中，对当前 Search / Trace 页面涉及到的静态文案做最小 patch。
- 静态文案与数据值明确分层：
  - 翻译：标签、按钮、提示、菜单、帮助文案、空态 / 错误态
  - 不翻译：service name、operation name、trace id、span id、session id、tag / attribute 的实际值

### 2. 页面落点

- Search 主路径：
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/App/TopNav.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/SearchForm.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/index.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/SearchResults/index.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/SearchResults/AltViewOptions.tsx`
- Trace 主路径：
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/AltViewOptions.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageSearchBar.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.tsx`
  - `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.tsx`

### 3. 可读性修复原则

- 颜色 patch 继续沿用 Jaeger 已有主题变量：
  - `var(--text-primary)`
  - `var(--text-secondary)`
  - `var(--surface-primary)`
  - `var(--surface-secondary)`
  - `var(--surface-tertiary)`
  - `var(--border-default)`
- 不允许再写死只对浅色模式友好的固定十六进制颜色。
- 如果需要提高对比度，优先通过：
  - 更高权重的主题变量覆盖
  - 更清晰的边框 / 背景层级
  - 中文文案长度引发的布局与间距修正

### 4. 构建与部署边界

- Jaeger UI 仍然从 vendored 源码 build。
- 集群镜像默认继续采用 runtime packaging 路线：
  - 先在仓库内把前端产物 build 出来
  - 再用一个极小 Docker context 打 `openagentic/jaeger-ui-proxy:v58` 这类 runtime 镜像
- 不把“在 Docker 内重新 source-build Jaeger UI”作为默认路径；它保留为可选 fallback。

## Acceptance (DoD)

必须全部满足：

1. Search 页面：
   - Search 页面的核心静态文案为简体中文
   - Search 页面的中文文本没有明显截断或布局破坏
2. Trace 页面：
   - Trace 页面的核心静态文案为简体中文
   - transcript panel 文案也切为简体中文
   - 点击 real trace span，transcript panel 仍能正常显示
3. 可读性：
   - 亮色主题下 Search / Trace 核心文本可读
   - 深色主题下 Search / Trace 核心文本也可读
   - 不再出现“为了亮色修复，结果深色再次看不清”的回归
4. 回归：
   - `oa chat --k3d-real` 不受影响
   - `http://127.0.0.1:16686` 不变
   - v58 transcript drilldown 仍可用
5. 文档：
   - build / runtime packaging / k3d 导入经验包已写入仓库
   - 命令、fallback 与常见卡点可被逐条核对

## Files

- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/App/TopNav.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/SearchForm.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/index.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/SearchResults/index.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/SearchTracePage/SearchResults/AltViewOptions.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/AltViewOptions.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageSearchBar.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.tsx`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/common/LabeledList.css`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.css`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.css`
- Modify: `third_party/jaeger-ui/packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.css`
- Create: `tests/test_v59_jaeger_ui_localization_assets.py`
- Create: `docs/prd/PRD-0059-jaeger-search-trace-zh-cn-v59.md`
- Create: `docs/plan/v59-index.md`
- Create: `docs/plan/v59-jaeger-search-trace-zh-cn.md`

## Milestones

### M1 — Search 页面中文化

- 顶部导航与 Search 页核心静态文案改为简体中文
- Search 结果区视图切换与空态 / 结果摘要一起收口
- 先保证“Search 页面读起来不费劲”

DoD：

- `python -m unittest -q tests.test_v58_jaeger_ui_assets tests.test_v59_jaeger_ui_localization_assets`
- 手工验证：
  - 打开 `http://127.0.0.1:16686`
  - Search 页面核心文案为中文
  - 中文文案未造成明显布局溢出

### M2 — Trace 页面中文化与可读性收口

- Trace header、视图切换、页内搜索帮助、span detail、transcript panel 改为简体中文
- 把 Search / Trace / transcript panel 的残余颜色问题一起修掉
- 显式验证深色 / 亮色主题都可读

DoD：

- `python -m unittest -q tests.test_actor_tracing tests.test_session_transcript_view tests.test_cluster_chat_transcript_api tests.test_remote_worker_transcript_api tests.test_v58_jaeger_ui_assets tests.test_v59_jaeger_ui_localization_assets`
- 手工验证：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
  - 打开 real trace
  - Trace 页面核心文案为中文
  - transcript panel 仍可显示正文
  - 切换深色 / 亮色主题后，关键文字仍清晰可读

### M3 — Jaeger 构建与部署经验包

- 把 v58/v59 这轮真实踩出来的构建与部署路径固化成经验包
- 给出主路径、fallback、常见卡点与诊断命令

DoD：

- 文档中明确包含：
  - Windows / WSL2 边界
  - runtime packaging 主路径
  - 最小 Docker context 原则
  - k3d 镜像导入 fallback
  - 常见“卡住”边界定位方法

## Build / Deploy Experience Pack

### 1. 环境职责边界

- PowerShell / Windows 侧更适合做：
  - 仓库编辑
  - Node 前端产物 build
  - `oa chat --k3d-real` 交互测试
- WSL2 侧更适合做：
  - Docker / k3d / kubectl
  - 镜像打包与集群导入
  - port-forward

### 2. 为什么不要把整个仓库直接丢给 Docker build

- vendored Jaeger UI 目录下如果带着 `node_modules`，context 会非常大。
- 这会导致：
  - `docker build` 长时间无响应
  - 误判为“镜像构建卡死”
  - 代理 / 拉取问题与 context 传输问题混在一起，边界不清
- 默认原则：
  - 先本地 build 静态产物
  - 再只把 `deploy/k8s/v58/*` 与 `third_party/jaeger-ui/.../build/` 放进极小 context 做 runtime packaging

### 3. 默认推荐：runtime packaging，而不是 Docker 内 source-build

- 推荐主路径：
  1. 在仓库内 build Jaeger UI 静态产物
  2. 使用 `deploy/k8s/v58/jaeger-ui-proxy.runtime.Dockerfile`
  3. 打出只负责托管静态文件与 nginx 代理的 runtime 镜像
- 原因：
  - Windows / WSL 混合环境下更稳
  - 避免把 upstream 的 Unix-only prepare 脚本问题带进 Docker 构建链
  - 构建边界更清晰：前端 build 与镜像 packaging 分离

### 4. k3d 镜像导入的主路径与 fallback

- 主路径：
  - 优先尝试 `k3d image import`
- fallback：
  - `docker save` 导出 tar
  - `docker cp` 进各个 k3d node 容器
  - `ctr -n k8s.io images import` 手动导入
- 当 `k3d image import` 遇到多架构镜像或导入不稳定时，直接切到 fallback，不要傻等。

### 5. 常见“卡住”场景与边界定位

- `docker build` 很久没输出：
  - 先怀疑 build context 过大，不要先怀疑 Docker daemon
- 宿主机提示没有 `docker` 命令：
  - 先确认这台机器的容器链路是不是在 WSL2 里，而不是继续在 Windows 侧重试
- Jaeger 页面是旧前端：
  - 先确认是否真的重新 build 了静态产物
  - 再确认 runtime 镜像是否重新打包并导入到了 k3d node
- port-forward 正常但页面行为没变：
  - 先检查 Pod 用的镜像 tag / digest
  - 不要先改业务代码

### 6. 固定入口约束

- 用户侧继续只记两件事：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
- 不为这轮中文化额外发明新入口命令。

## Notes

- v59 的核心不是“全量国际化”，而是优先把真实高频调试路径变成中文可读。
- 文案 patch 与主题 patch 必须一起做；只做文案不看布局 / 对比度，后面还是会返工。
- 对 Search / Trace 而言，“值保持原样、标签翻译成中文”是最稳的边界。
- build / deploy 经验包不是附属品；它本身就是这轮交付的一部分，因为这条链路已经证明足够容易失忆和返工。
