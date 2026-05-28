# civ-core · frontend

筑核桌面壳 + 前端：Tauri 2.11 主进程（Rust） + React 19 + TypeScript + Tailwind v4。

> **定位**：这是 `civ-core` 仓库的 GUI 入口，不是独立项目。架构 / 路由 / RPC 约定在仓库根目录的 [`CLAUDE.md`](../CLAUDE.md) 和 [`../.ai/RULES.md`](../.ai/RULES.md)；本目录的编码约定在 [`CLAUDE.md`](CLAUDE.md)。

---

## 跑

```bash
# 一次性
npm install

# Dev（同时拉起 Tauri 主进程 + Vite + 双 sidecar）
npm run tauri:dev
```

前置依赖：Node 20+、Rust toolchain、`dotnet build` 已跑过、`uv sync` 已跑过。详见根目录 `README.md`。

## 测试

```bash
npx tsc -b --noEmit      # 类型检查
npm run lint             # ESLint
npm run format:check     # Prettier
```

## 目录结构（节选）

```
src/
├── App.tsx                  顶层壳：Provider 嵌套 + 布局
├── components/              VSCode 风格布局组件（TitleBar / SideBar / ...）
├── lib/                     rpc.ts / shell.ts 等基础设施
└── tools/                   每个工具一个目录（controller / Page / SettingsForm）
    ├── _shared/             跨工具公共组件（CatalogDrivenInputs / forms / ...）
    ├── data_processing/
    ├── plot_curves/
    ├── report_generator/
    ├── template_helper/
    ├── pdf_tools/
    └── word2pdf/
src-tauri/                   Tauri 主进程（Rust）：sidecar.rs + lib.rs
```

工具页范式（Controller / Page / SettingsForm 模板）见 [`CLAUDE.md`](CLAUDE.md)。
