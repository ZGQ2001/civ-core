# docs 优先级索引

> 按影响面和紧迫度排序。P0 = 工程安全 / 数据正确性，P1 = 稳定性 / 用户体验，P2 = 体验优化，P3 = 长期规划。

---

## audit 专项（2026-05-24 鲁棒性审查）

收敛报告：`audit/2026-05-24-00-收敛报告.md`（总览，6P0 + 6P1 + 7P2）

| 优先级 | 文件 | 核心问题 | 状态 |
| ------ | ---- | -------- | ---- |
| **P0** | `audit/2026-05-24-02-RPC输入校验缺口.md` | 锚杆物理参数无正值校验；PreviewExcel 无文件检查 | DONE (正值校验已有；文件检查已加) |
| **P0** | `audit/2026-05-24-06-意外关机与崩溃恢复.md` | C# SaveAs 直接覆盖，断电损坏输出文件 | DONE (AtomicFile.SaveWorkbook) |
| **P0** | `audit/2026-05-24-01-土木工程师不可读报错.md` | C# 14 处程序术语泄漏 + 前端无翻译层 | DONE (handler 中文化 + rpc.ts translateError + -32602 分流) |
| **P1** | `audit/2026-05-24-04-点击顺序错误.md` | 计算中切换模式无 abort，旧结果写错 state | WONTFIX (reqIdRef 已防数据串位；真 abort 需 sidecar 支持) |
| **P1** | `audit/2026-05-24-03-按钮防重复点击.md` | 预设操作 + FileTree 粘贴/撤销无 running 守卫 | DONE (busy 状态守卫) |
| **P2** | `audit/2026-05-24-05-数据格式有误.md` | 错误码统一 -32603（应 -32602） | DONE (-32602 分流已加) |
| **P2** | `audit/2026-05-24-07-大文件与内存.md` | Excel 全量加载无上限守卫 | DONE (FileGuard.CheckExcelSize > 50MB 拦截) |

### 下一步

1. **P1 - abort 机制**：各 controller 加 `cancel()` + AbortController
2. **P1 - 按钮守卫**：预设操作 + FileTree 加 operationInProgress 状态
3. **P2 按空闲插入**

---

## plans 技术方案

| 优先级 | 文件 | 内容 | 前置条件 | 预估工期 |
| ------ | ---- | ---- | -------- | -------- |
| ~~**P1**~~ DONE | `plans/2026-05-29-template-editor.md`（plan 已删） | 报告填充走通：占位符引擎 `{{}}` v2 + `{{img:xxx}}` + 成对 marker + report_generator 独立工具页 | —— | 3 commit 落地（2026-05-26） |
| **P3** | `plans/2026-05-23-electron-migration-rich-preview.md` | Tauri -> Electron 迁移 + 富格式预览（Excel/PDF） | 无硬性前置，但改动面大 | 15-20 天（3 阶段） |

### 说明

- **报告填充（原 P1，已交付）**：实际走「用户写 `{{占位符}}` + 程序填充」而非「可视化绑定」路径——更简单、用户认知负担更小、跟"模板由甲方定"的领域特性更契合。详见 `.ai/PROGRESS.md` T5.6 + commit `2b83c41` / `a3e2eb9` / `a1c74ee` / `228b0cf`。
- **Electron 迁移（P3）**：架构层面的改善，不影响当前功能交付。Tauri 目前能用，迁移动机是降低 Rust 维护门槛和支持富预览。建议作为后续候选，按用户优先级排。
