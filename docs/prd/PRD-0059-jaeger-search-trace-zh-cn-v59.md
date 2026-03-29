# PRD-0059 — Jaeger Search / Trace 中文化与页面收口 v59

## Vision

v59 的目标不是把整个 Jaeger UI 一口气全部汉化，而是先把当前实际高频使用的 `Search` 与 `Trace` 两个页面做成“中文可读、主题安全、便于继续调试”的状态：

- `Search` 页面中的核心静态文案改为简体中文；
- `Trace` 页面中的核心静态文案改为简体中文；
- v58 已经补进去的 transcript panel，也要顺手纳入中文文案与可读性收口范围；
- 当前已经暴露出来的 Search / Trace 页面残余颜色与对比度问题要一起修掉，而且不能只对亮色主题生效；
- 用户入口仍然保持不变：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
- 同时，把这轮 Jaeger UI 构建、runtime packaging、WSL / k3d 导入镜像的实际经验，固化成仓库内可复用的“经验包”，防止后续再次踩同样的坑。

## Non-Goals

- v59 不做整个 Jaeger 产品的全量国际化。
- v59 不引入新的语言切换系统、locale provider 或运行时多语言框架。
- v59 不改 tracing 协议、`oa.*` span 字段、transcript API、session store 结构。
- v59 不改 `oa chat --k3d-real`、Jaeger 固定地址、现有 k3d cluster 语义。
- v59 不翻译 trace / service / operation 的业务数据值；只翻译 UI 静态文案。
- v59 不触碰 `Compare`、`System Architecture`、`Monitor` 等页面的完整正文翻译；这些页面后续再单独版本化处理。

## Requirements

### REQ-0059-001 — Search 页面核心静态文案必须切换为简体中文

- Search 页面的核心用户可见静态文案必须改为简体中文，至少覆盖：
  - 顶部导航中与当前使用路径直接相关的核心入口文案
  - 查询表单标签、placeholder、lookback 选项、按钮文本
  - Search 结果区的视图切换、空态、错误态、结果摘要等核心文案
- 服务名、operation 名、trace id、tag value 这类数据值保持原样，不做翻译。

### REQ-0059-002 — Trace 页面核心静态文案必须切换为简体中文

- Trace 页面的核心用户可见静态文案必须改为简体中文，至少覆盖：
  - Trace header 概览区
  - Trace view 切换菜单
  - in-page search / locate / previous / next 相关文案与帮助说明
  - span detail 中的关键标签
  - v58 transcript panel 中的标题、状态、错误与元信息标签
- trace 名称、service 名称、operation 名称、span id、session id 等值保持原样，不做翻译。

### REQ-0059-003 — Search / Trace 页面剩余可读性问题必须一起收口

- v59 必须把当前 Search / Trace 页面里已经暴露出的残余颜色与对比度问题一起修掉。
- 修复必须是主题安全的：
  - 亮色主题可读
  - 深色主题可读
- 不允许再写死只适合浅色背景的颜色值，导致深色主题下文字再次看不清。

### REQ-0059-004 — 当前入口、协议与部署语义不得被破坏

- `oa chat --k3d-real` 继续保持不变。
- Jaeger 继续保持固定地址 `http://127.0.0.1:16686`。
- transcript 同源代理语义保持不变：
  - 浏览器仍然只访问 `16686`
  - `/oa/transcript/...` 仍然通过同源代理进入 host
- v58 的 transcript drilldown 行为不得被本轮中文化破坏。

### REQ-0059-005 — 必须提供可重复验证的中文化与页面回归证据

- 仓库内必须增加针对 Jaeger UI 中文化 / 主题安全 patch 的静态资产测试。
- 至少要能验证：
  - Search / Trace 关键文案已替换
  - Search / Trace / transcript panel 的可读性 patch 不再依赖硬编码浅色值
  - v58 transcript panel patch 仍在
- 还必须保留一套手工验证路径，用于 real cluster 中确认：
  - Search 页面中文化真实可见
  - Trace 页面中文化真实可见
  - Transcript panel 仍可用
  - 深浅主题都能看清

### REQ-0059-006 — Jaeger UI 构建与部署经验必须沉淀为仓库内经验包

- v59 必须把本轮已经验证过的 Jaeger UI 构建 / 打包 / 导入集群经验写入仓库文档。
- 经验包至少要覆盖：
  - Windows 宿主与 WSL2 的职责边界
  - 为什么不直接把整个仓库作为 Docker build context
  - 为什么默认采用 runtime packaging，而不是在 Docker 内重新 source-build
  - k3d / containerd 镜像导入的主路径与 fallback 路径
  - 常见卡住点、对应边界定位方法与推荐命令

### REQ-0059-007 — v59 patch 必须继续保持最小、可审计、可回放

- 本轮中文化与可读性 patch 仍然必须落在仓库内 vendored Jaeger UI 源码之上。
- 不允许引入运行时远程脚本注入或不可追溯的临时替换方案。
- 本轮 patch 必须继续能从仓库内源码重复 build 与打包出来。
