---
name: civ-core-dev
description: civ-core（筑核）土木检测内业报告自动化项目的入门工作流。涉及 civ-core / 筑核 / 锚杆抗拔 / 报告填充 / 装配线 / sidecar / OpenXML / Tauri+Rust+C#+Python 多语言栈的任务时触发。给出会话启动 SOP，把 Claude 路由到正确的项目文档。
---

# civ-core 工作流入口

**核心原则**：本 skill 不复述项目状态。仓库本身的 `CLAUDE.md` / `.ai/*` 是 single source of truth，会随代码演进自动保持最新。本 skill 只负责把你**带到正确的入口**并执行检查清单。

## 会话启动 SOP

任何 civ-core 任务开始前，按顺序执行：

### 1. 读 3 份文档（不可跳过）

```
CLAUDE.md                 # 宪法：架构 + 路由 + 不可变规则
.ai/CONTEXT.md            # 当前焦点 + 用户偏好 + UX 缺口（每会话更新）
.ai/RULES.md              # 编码规范 + RPC 清单 + 技术债
```

如果改动涉及 C#：再读 `dotnet/CLAUDE.md`。
如果改动涉及前端：再读 `frontend/CLAUDE.md`。

### 2. 用 git 看现状

```bash
git status              # 是否有未 commit 改动
git log --oneline -5    # 最近 5 个 commit 风格
```

**禁止**：会话开始就 `git add` / `git commit`（除非用户明确要求）。

### 3. 把任务路由到对应 skill

| 任务类型 | 用 skill |
|---------|---------|
| 做 MCP server / 暴露 sidecar 给 agent | [[civ-core-mcp-tools]] |
| 加新检测类型（钻芯 / 回弹 / 新规范） | [[civ-core-add-detection-type]] |
| 帮用户做 Word 模板 | [[civ-core-make-template]] |
| 排查 sidecar / RPC bug | [[civ-core-debug-rpc]] |
| 写锚杆 / 钻芯计算逻辑 | [[civ-core-anchor-calc]] |
| 引用土木规范 | [[civil-codes-vault]] |
| 通用 C# 后端工作 | 用户级 csharp-* skill 会自动激活 |

## 任务执行清单（每步可验证）

按 CLAUDE.md「行为准则」第 4 条「跑通才算完」：

- [ ] 任务转成可验证目标（"加校验" → "先写失败测试，再让它过"）
- [ ] 改动符合依赖方向（前端 → Tauri → sidecar → core，不可反转）
- [ ] 改完跑 `npx tsc -b --noEmit` / `dotnet build` / `dotnet test`
- [ ] UI 改动跑一次 `npm run tauri:dev` 人肉验证
- [ ] 大需求拆多次 commit，每次独立验收（用户偏好）
- [ ] 不顺手改无关代码（CLAUDE.md 准则 3「手术刀改动」）

## 完工前检查

```
1. 跑通了吗？      （tsc / dotnet test / 浏览器烟测）
2. 改动范围对吗？  （只动任务相关，没顺手清理 dead code）
3. CONTEXT.md 要更新吗？（里程碑 / 用户偏好新增 → 更新）
4. commit message 风格？（中文 feat:/fix:/refactor: + Co-Authored-By）
5. push 等用户拍板（不自动 push）
```

## 常见陷阱（跨项目重复出现的）

详细诊断在 [[civ-core-debug-rpc]]，这里只列**最容易踩**的：

1. **Python handler 缺 `__all__`** → `import Path` 暴露成 RPC 方法（CLAUDE.md 不可变规则 2）
2. **前端 `run()` 没 return 值** → handleRun 永远拿不到结果（HandleRun stale closure pitfall）
3. **stdout 被写日志** → 协议流被污染（用 `Console.Error.WriteLine` / stderr file logger）
4. **改 catalog 字段维度没改 RPC 入参** → 前端发 batch_user_inputs 但 handler 不解析
5. **新加 RPC handler 没 `dispatcher.Register`** → 前端报"未知 method"

## 不要做

- 不要复述 CLAUDE.md 内容到自己的回复里（用户能自己读，浪费 token）
- 不要在没看 CONTEXT.md 的情况下假设当前焦点
- 不要因为 skill 列出了某个工作流就跳过用户的具体指令——skill 是默认 SOP，用户指令永远优先
