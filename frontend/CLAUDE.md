# 前端域规则

> **角色**：仅在 AI 操作 `frontend/src/` 目录时加载。放前端专属编码规范。
> **主宪法**：`../CLAUDE.md`（架构/路由/不可变规则）

---

## 技术栈

Vite + React 19 + TypeScript + Tailwind v4 + @vscode/codicons + react-resizable-panels

## 工具页范式

所有工具页统一结构（当前 6 个：data_processing / plot_curves / report_generator / template_helper / pdf_tools / word2pdf）：

```
tools/<tool>/
├── index.ts           export { Provider, Page, SettingsForm }
├── types.ts           State / Actions / Ctx 类型
├── controller.tsx     createContext + Provider + 状态管理
├── Page.tsx           主界面（中间预览区）
└── SettingsForm.tsx   右侧参数区（在 RightPanel 内渲染）
```

**工具装配唯一来源**：工具的 ActivityBar 项 / 中间页路由 / 右侧调参 tab / Provider 挂载全部在 `tools/registry.tsx` 的 `TOOLS` + `TOOL_PROVIDERS` 注册一次，App.tsx / EditorArea 从中派生。**加工具只改 registry 两个数组，App.tsx 不动**；别再在 App 里散写 `activeToolId === 'x' ? ...` 之类的枚举。

**工具间耦合原则**：工具之间不通过 useXxxCtrl() 隐式继承上游 state（曾经 report_generator 直接 useDataProcessing 是反例，已改）。如果工具 B 想消费工具 A 的输入，提供「一键导入 A」按钮 —— 经 `ShellContext` 的快照（如 `dataProcessingSnapshot`）显式拷贝到 B 自己的 state，B 不直接 `useXxx` 上游。这样：

- 工具 B 能独立挂载/工作（用别人的输入 / 测试隔离，不依赖 Provider 嵌套顺序）
- 装配线连贯（用户一键就能继承上游已填的）
- 状态变化追溯清晰（不会"上游一变下游莫名重渲染"）

### Controller 模板

```tsx
// controller.tsx
interface State { running: boolean; runError: string | null; previewLoading: boolean; ... }
interface Actions { run(): Promise<RunRes | null>; ... }
interface RunRes { summary: string; ... }

const Ctx = createContext<(State & Actions) | null>(null);

export function Provider({ children }: { children: ReactNode }) {
    const [state, setState] = useState<State>({ ... });
    const reqIdRef = useRef(0);

    const actions: Actions = useMemo(() => ({
        async run() {
            setState(s => ({ ...s, running: true, runError: null }));
            try {
                const data = await rpc<RunRes>("tool.run", { ... });
                setState(s => ({ ...s, running: false }));
                return data;  // ← 必须 return！Page.tsx 依赖这个返回值
            } catch (e) {
                setState(s => ({ ...s, running: false, runError: String(e) }));
                return null;
            }
        },
        // ...
    }), [/* deps */]);

    return <Ctx.Provider value={{ ...state, ...actions }}>{children}</Ctx.Provider>;
}

export function useXxxCtrl() {
    const v = useContext(Ctx);
    if (!v) throw new Error("useXxxCtrl must be inside Provider");
    return v;
}
```

### Page 模板

```tsx
// Page.tsx
export function Page({ appendOutput }: { appendOutput?: (line: string) => void }) {
    const c = useXxxCtrl();

    // ✅ run() 内部统一把成功/失败写进输出面板（appendOutput）；Page 只用 run() 的返回值。
    const handleRun = useCallback(async () => {
        const res = await c.run();
        if (res) appendOutput?.(`完成：${res.summary}`);
        // 失败已由 run() 内部记录，不在此读 c.runError
    }, [c, appendOutput]);

    // ❌ 禁止：await c.run() 之后读 c.runError / c.result（都是陈旧闭包值）
    //    需要错误详情就让 run() 返回判别联合（plot/pdf/word 即如此），别读闭包 state

    return (/* JSX */);
}
```

### SettingsForm 模板

```tsx
// SettingsForm.tsx
export function SettingsForm() {
  const c = useXxxCtrl();
  return <div className="space-y-4 p-3">{/* 参数表单 */}</div>;
}
```

## RPC 调用

```tsx
// lib/rpc.ts
export async function rpc<T>(
  method: string,
  params?: Record<string, unknown>,
  schema?: ZodType<T>, // 可选：传则运行时校验返回值
): Promise<T>;
```

**运行时校验**：不传 `schema` 时 `as T` 无运行时校验（非关键方法用）。出错代价高的核心方法**必须**传 zod schema——校验失败抛「后端返回格式异常」，把契约漂移在边界显式化（而非渲染时静默炸 / 出错报告）。schema 集中在 `lib/rpcSchemas.ts`（唯一来源），当前覆盖 `anchor.run` / `report.run_from_result` / `catalog.get`。新增核心方法时一并加 schema。

## 布局约束

```
TitleBar (30px)
[ActivityBar(48) | SideBar(全高) | (Editor + 底部 Panel) | RightPanel(全高)]
StatusBar (22px)
```

- SideBar：全高，不被底部 Panel 截断
- 底部 Panel：专用「输出/日志」Tab；Ctrl+J toggle
- RightPanel：全高，tab 化（当前工具调参 + AI 助手占位）；Ctrl+Alt+B toggle
- 工具页：中间上部预览区 + 右侧参数区（RightPanel）

## 样式

- Tailwind v4，暗色主题（`bg-[#1e1e1e]` 基底）
- 图标：@vscode/codicons，只用包里真实存在的名字（~649 个；`../.ai/RULES.md` 列常用，非穷举，拿不准查 `node_modules/@vscode/codicons/dist/codicon.css`）
- 禁 emoji（UI/commit/AI 文档）
- 原生控件深色：`index.css` 已设 `html { color-scheme: dark }`

## 公共组件

| 文件                                    | 内容                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tools/_shared/forms.tsx`               | **所有工具页唯一控件来源**：`ToolHeader`（统一顶栏：同底色/padding/标题）、`Field` / `Picker` / `ResetBtn`、`RunBtn`（统一运行主按钮）、`IconBtn`（统一小图标钮，`bordered` 变体）、`Select` + `INPUT_CLS`（统一下拉/输入 + `focus:border-vscode-focus` 焦点环）、`ErrorBanner`（统一报错卡 `role="alert"` + 可选「重试」恢复）。新工具/新控件先看这里有没有现成的，别重抽。 |
| `components/Dialogs.tsx`                | `DialogsProvider` + `useDialogs()`：promise 化统一弹窗（`confirm` / `prompt` / `alert`），取代全项目 `window.confirm/prompt/alert`。`main.tsx` 根级挂载；Esc 取消 / Enter 确认 / 点遮罩取消。                                                                                                                                                                                |
| `tools/_shared/anchorParamsForm.tsx`    | 锚杆按批次工程参数 UI（P/Lf/La/A/E 5 字段 × N 批次折叠卡片）。data_processing 和 report_generator 通过 props 传 batchIds / paramsByBatch / setter 复用。                                                                                                                                                                                                                     |
| `tools/_shared/CatalogDrivenInputs.tsx` | 报告填充「项目元信息」公共渲染器：按 `catalog.get` 动态拉字段定义，按 level → group 分组渲染 user_input（仅 `source==='userinput'`，无下划线，与 C# 序列化对齐）。模板助手改字段，报告填充立刻同步。接 `historyByKey` prop 显示历史值下拉。                                                                                                                                  |

## 快捷键

| 快捷键     | 功能              |
| ---------- | ----------------- |
| Ctrl+B     | toggle SideBar    |
| Ctrl+J     | toggle 底部 Panel |
| Ctrl+Alt+B | toggle RightPanel |

## 构建

```bash
cd frontend
npm install                     # 装依赖
npx tsc -b --noEmit             # TS 类型检查
npm run build                   # 生产构建
npm run tauri:dev               # 开发模式（Tauri + Vite + Python/C# sidecar）
```
