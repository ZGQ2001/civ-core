# 计划：迁移 Tauri → Electron + 富格式文档预览

## Context

**为什么换 Electron：**
- Rust 门槛高，AI 写主进程易出错，CI 审查成本高
- Node.js 主进程对 AI 和人类都更易维护调试
- 不依赖 WebView2，对旧机器和未来跨平台友好
- C# + Python sidecar 通信协议不变，迁移只涉及主进程层

**设计原则（参考 VS Code）：**
- **物理隔离**：主进程 / 渲染进程 / 各 sidecar 各占独立 OS 进程，互不共享内存
- **并发异步**：多请求同时在途，按 ID 匹配响应，不强制串行
- **彻底解耦**：Router 独立类，路由配置与 main.ts 分离；前端 IPC 集中在 `ipc.ts` 一处
- **规范协议**：JSON-RPC 2.0 over newline-delimited stdin/stdout，前端→主进程走结构化 contextBridge 命名空间

---

## 第一阶段：Electron 架构

### 目录结构

```
frontend/
├── electron/
│   ├── protocol.ts     # 协议类型定义（RpcRequest / RpcResponse / IpcApi）
│   ├── sidecar.ts      # JsonRpcSidecar：物理进程管理 + 并发异步 transport
│   ├── router.ts       # RpcRouter：可注册路由，解耦 main.ts
│   ├── main.ts         # 装配入口：创建 sidecar + 注册路由 + 挂 ipcMain
│   └── preload.ts      # 命名空间 contextBridge（不暴露 Node/Electron 原生）
└── src/
    ├── lib/
    │   ├── ipc.ts      # 前端唯一 IPC 出口（所有 electronAPI 调用汇聚于此）
    │   ├── rpc.ts      # 薄包装：export rpc = ipc.rpc（工具页不改 import）
    │   └── shell.ts    # 替换 opener
    └── electron.d.ts   # window.electronAPI 类型声明
```

---

### `electron/protocol.ts`

协议层类型，与具体实现无关：

```typescript
// JSON-RPC 2.0 消息类型
export interface RpcRequest {
  jsonrpc: '2.0';
  id: number;
  method: string;
  params: unknown;
}

export interface RpcResponse {
  jsonrpc: '2.0';
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

// contextBridge 暴露的命名空间 API 契约
export interface IpcApi {
  rpc: {
    call(method: string, params: unknown): Promise<unknown>;
  };
  dialog: {
    open(opts: Electron.OpenDialogOptions): Promise<string[]>;
    save(opts: Electron.SaveDialogOptions): Promise<string | null>;
  };
  shell: {
    openPath(path: string): Promise<void>;
  };
  // 注意：不暴露任意 fs 读取接口。
  // 本地文件通过 civ-file:// 自定义协议流式访问（见 main.ts）。
  window: {
    minimize(): void;
    maximize(): void;
    close(): void;
  };
}

// 将绝对路径转换为 civ-file:// URL（前端调用，不经过 IPC）
export function civFileUrl(absPath: string): string {
  const posix = absPath.replace(/\\/g, '/');
  const withSlash = posix.startsWith('/') ? posix : `/${posix}`;
  return `civ-file:/${withSlash}`;
}
```

---

### `electron/sidecar.ts`

物理进程隔离 + 并发异步 transport（多请求同时在途，按 ID 匹配）：

```typescript
import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import type { RpcRequest, RpcResponse } from './protocol';

const DEFAULT_TIMEOUT_MS = 30_000;

interface PendingRequest {
  resolve(v: unknown): void;
  reject(e: Error): void;
  timer: NodeJS.Timeout;
}

export class JsonRpcSidecar extends EventEmitter {
  private proc!: ChildProcess;
  private pending = new Map<number, PendingRequest>();
  private nextId = 0;
  private buf = '';
  readonly name: string;

  constructor(
    name: string,
    private readonly command: string,
    private readonly args: string[],
    private readonly cwd?: string,
  ) {
    super();
    this.name = name;
    this.start();
  }

  private start() {
    this.proc = spawn(this.command, this.args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: this.cwd,
    });

    this.proc.stdout!.setEncoding('utf8');
    this.proc.stdout!.on('data', (chunk: string) => {
      this.buf += chunk;
      const lines = this.buf.split('\n');
      this.buf = lines.pop()!;
      for (const line of lines) {
        if (!line.trim()) continue;
        try { this.dispatch(JSON.parse(line)); }
        catch { process.stderr.write(`[${this.name}] bad JSON: ${line}\n`); }
      }
    });

    // stderr 原样转发，不污染协议流
    this.proc.stderr!.on('data', (d: Buffer) =>
      process.stderr.write(`[${this.name}] ${d}`)
    );

    this.proc.on('exit', (code) => {
      // 进程退出：reject 所有在途请求
      for (const [, p] of this.pending) {
        clearTimeout(p.timer);
        p.reject(new Error(`Sidecar '${this.name}' exited (code ${code})`));
      }
      this.pending.clear();
      this.emit('exit', code);
    });
  }

  call(method: string, params: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC timeout (${timeoutMs}ms): ${this.name}/${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });

      const req: RpcRequest = { jsonrpc: '2.0', id, method, params };
      this.proc.stdin!.write(JSON.stringify(req) + '\n');
    });
  }

  private dispatch(msg: RpcResponse) {
    const p = this.pending.get(msg.id);
    if (!p) return;
    clearTimeout(p.timer);
    this.pending.delete(msg.id);
    msg.error
      ? p.reject(new Error(msg.error.message))
      : p.resolve(msg.result);
  }

  kill() {
    // 给 sidecar 机会优雅退出（关 stdin 触发 EOF），1s 后强杀
    try { this.proc.stdin!.end(); } catch {}
    setTimeout(() => {
      try { this.proc.kill('SIGKILL'); } catch {}
    }, 1000).unref();
  }
}
```

---

### `electron/router.ts`

可注册路由，与 main.ts 解耦：

```typescript
import { JsonRpcSidecar } from './sidecar';

export interface RouteConfig {
  sidecar: JsonRpcSidecar;
  prefixes?: string[];
  exact?: string[];
}

export class RpcRouter {
  private routes: RouteConfig[] = [];

  constructor(readonly defaultSidecar: JsonRpcSidecar) {}

  register(config: RouteConfig) {
    this.routes.push(config);
    return this;
  }

  route(method: string): JsonRpcSidecar {
    for (const r of this.routes) {
      if (r.exact?.includes(method)) return r.sidecar;
      if (r.prefixes?.some(p => method.startsWith(p))) return r.sidecar;
    }
    return this.defaultSidecar;
  }

  call(method: string, params: unknown): Promise<unknown> {
    return this.route(method).call(method, params);
  }
}
```

---

### `electron/main.ts`

#### Blocker 修复汇总：
1. **孤儿进程防护**：`app.on('quit')` + `process.on('exit')` + `uncaughtException` 三重兜底
2. **生产路径**：`app.isPackaged` 分支，生产走 `process.resourcesPath`
3. **大文件流式加载**：注册 `civ-file://` 自定义协议，PDF 用流式访问，不走 IPC Buffer
4. **路径沙盒**：`civ-file://` 协议处理器内校验路径在允许范围内
5. **sandbox 开启**：`sandbox: true`（preload 由 vite 完整打包，无需裸 require）

```typescript
import { app, BrowserWindow, ipcMain, dialog, shell, protocol, net, session } from 'electron';
import path from 'path';
import os from 'os';
import { JsonRpcSidecar } from './sidecar';
import { RpcRouter } from './router';

// ── 必须在 app.ready 之前注册自定义协议 ────────────────────────────
protocol.registerSchemesAsPrivileged([{
  scheme: 'civ-file',
  privileges: {
    standard: true,
    secure: true,
    stream: true,          // 关键：允许 pdfjs 使用 Range 请求分片加载
    supportFetchAPI: true,
    bypassCSP: false,
  },
}]);

// ── 路径解析（开发 vs 生产）─────────────────────────────────────────
function getSidecarPaths(root: string) {
  if (app.isPackaged) {
    const res = process.resourcesPath;
    return {
      // electron-builder extraResources 释放到 resources/ 下
      csharpCmd: path.join(res, 'civ-doc', 'civ-doc.exe'),   // dotnet publish self-contained
      csharpArgs: [] as string[],
      pythonCmd: path.join(res, 'civ_core', 'civ_core.exe'), // PyInstaller bundle
      pythonArgs: [] as string[],
    };
  }
  return {
    csharpCmd: 'dotnet',
    csharpArgs: ['exec', path.join(root, 'dotnet/civ-doc/bin/Debug/net9.0/civ-doc.dll'), '--root', root],
    pythonCmd: 'uv',
    pythonArgs: ['run', 'python', '-m', 'civ_core.api', '--root', root],
  };
}

// ── 路径沙盒校验（civ-file:// 用）───────────────────────────────────
let currentWorkspacePath: string | null = null;

function isPathAllowed(absPath: string): boolean {
  const normalized = path.resolve(absPath);
  const allowedRoots = [
    os.tmpdir(),
    app.getPath('userData'),
    currentWorkspacePath,
  ].filter(Boolean).map(p => path.resolve(p!));
  return allowedRoots.some(root =>
    normalized === root || normalized.startsWith(root + path.sep)
  );
}

// ── 主流程 ────────────────────────────────────────────────────────────
let mainWindow: BrowserWindow;
let router: RpcRouter;
const allSidecars: JsonRpcSidecar[] = [];

function killAllSidecars() {
  allSidecars.forEach(s => s.kill());
}

// 三重孤儿进程防护
app.on('quit', killAllSidecars);
process.on('exit', killAllSidecars);
process.on('uncaughtException', (err) => {
  process.stderr.write(`[main] uncaught: ${err.stack ?? err}\n`);
  killAllSidecars();
  app.exit(1);
});

app.whenReady().then(() => {
  const root = path.resolve(__dirname, '../..');
  const paths = getSidecarPaths(root);

  const csharp = new JsonRpcSidecar('csharp', paths.csharpCmd, paths.csharpArgs, root);
  const python = new JsonRpcSidecar('python', paths.pythonCmd, paths.pythonArgs, root);
  allSidecars.push(csharp, python);

  router = new RpcRouter(csharp).register({
    sidecar: python,
    prefixes: ['workspace.', 'files.', 'plot_curves.', 'pdf_tools.', 'word2pdf.'],
    exact: ['ping', 'version'],
  });

  mainWindow = new BrowserWindow({
    width: 1280, height: 800,
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,   // 启用 Chromium 沙盒；preload 由 vite 打包无需裸 require
    },
  });

  // ── 注册 civ-file:// 协议（流式本地文件访问，替代 IPC 传 Buffer）──
  // 该协议仅允许访问 workspace 和 temp 目录，防止任意文件读取
  session.defaultSession.protocol.handle('civ-file', (request) => {
    const url = new URL(request.url);
    let filePath = decodeURIComponent(url.pathname);
    // Windows: /C:/foo/bar → C:/foo/bar
    if (process.platform === 'win32' && /^\/[A-Za-z]:/.test(filePath)) {
      filePath = filePath.slice(1);
    }
    if (!isPathAllowed(filePath)) {
      return new Response('Forbidden', { status: 403 });
    }
    const fileUrl = `file:///${filePath.replace(/\\/g, '/')}`;
    return net.fetch(fileUrl);
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  devUrl
    ? mainWindow.loadURL(devUrl)
    : mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
});

// ── IPC 处理器（命名空间对应 preload）────────────────────────────────
ipcMain.handle('rpc:call', async (_e, method: string, params: unknown) => {
  const result = await router.call(method, params);
  // 追踪工作区路径以更新沙盒白名单
  if (method === 'workspace.set' || method === 'workspace.last') {
    const r = result as { path?: string } | null;
    if (r?.path) currentWorkspacePath = r.path;
  }
  return result;
});

ipcMain.handle('dialog:open', (_e, opts: Electron.OpenDialogOptions) =>
  dialog.showOpenDialog(mainWindow, opts).then(r => r.filePaths)
);
ipcMain.handle('dialog:save', (_e, opts: Electron.SaveDialogOptions) =>
  dialog.showSaveDialog(mainWindow, opts).then(r => r.filePath ?? null)
);
ipcMain.handle('shell:open-path', (_e, p: string) => shell.openPath(p));
// 注意：不注册 fs:read-bytes，文件通过 civ-file:// 协议访问

ipcMain.on('window:minimize', () => mainWindow.minimize());
ipcMain.on('window:maximize', () =>
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize()
);
ipcMain.on('window:close', () => mainWindow.close());
```

---

### `electron/preload.ts`

命名空间隔离，不暴露任何 Node/Electron 原生对象（无 `fs`）：

```typescript
import { contextBridge, ipcRenderer } from 'electron';
import type { IpcApi } from './protocol';

const api: IpcApi = {
  rpc: {
    call: (method, params) => ipcRenderer.invoke('rpc:call', method, params),
  },
  dialog: {
    open: (opts) => ipcRenderer.invoke('dialog:open', opts),
    save: (opts) => ipcRenderer.invoke('dialog:save', opts),
  },
  shell: {
    openPath: (p) => ipcRenderer.invoke('shell:open-path', p),
  },
  window: {
    minimize: () => ipcRenderer.send('window:minimize'),
    maximize: () => ipcRenderer.send('window:maximize'),
    close: () => ipcRenderer.send('window:close'),
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
```

---

### `frontend/src/electron.d.ts`

```typescript
import type { IpcApi } from '../../electron/protocol';

declare global {
  interface Window {
    electronAPI: IpcApi;
  }
}
```

---

### `frontend/src/lib/ipc.ts`（新建）

前端唯一 IPC 出口。本地文件访问通过 `civFileUrl()` 转换为 `civ-file://` URL，不经过 IPC：

```typescript
import { civFileUrl } from '../../electron/protocol';

export { civFileUrl };  // 供 PdfViewer 直接构造 URL，不走 IPC

export const ipc = {
  rpc: <T>(method: string, params?: unknown): Promise<T> =>
    window.electronAPI.rpc.call(method, params ?? {}) as Promise<T>,

  dialog: {
    open: (opts: Parameters<Window['electronAPI']['dialog']['open']>[0]) =>
      window.electronAPI.dialog.open(opts),
    save: (opts: Parameters<Window['electronAPI']['dialog']['save']>[0]) =>
      window.electronAPI.dialog.save(opts),
  },

  shell: { openPath: (p: string) => window.electronAPI.shell.openPath(p) },

  window: {
    minimize: () => window.electronAPI.window.minimize(),
    maximize: () => window.electronAPI.window.maximize(),
    close: () => window.electronAPI.window.close(),
  },
} as const;
```

### `frontend/src/lib/rpc.ts`

```typescript
import { ipc } from './ipc';
export const rpc = ipc.rpc;
// FileEntry、WorkspaceLast 等类型定义保持不变
```

### 其他前端改动

**`shell.ts`**：`openPath` → `ipc.shell.openPath`

**`TitleBar.tsx`**：
- 拖拽区：`data-tauri-drag-region` → CSS `style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}`，按钮区加 `WebkitAppRegion: 'no-drag'`
- 窗口控制：`getCurrentWindow().minimize()` → `ipc.window.minimize()` 等
- 删除 `import { getCurrentWindow } from '@tauri-apps/api/window'`

**4 个工具 Page / SettingsForm 的 dialog**：
```typescript
// 旧：import { open as openDialog } from '@tauri-apps/plugin-dialog';
// 新：
const paths = await ipc.dialog.open({ properties: ['openFile', 'multiSelections'], filters: [...] });

// 旧：import { save as saveDialog } from '@tauri-apps/plugin-dialog';
// 新：
const p = await ipc.dialog.save({ filters: [...] });

// 旧：import { openPath } from '@tauri-apps/plugin-opener';
// 新：
await ipc.shell.openPath(path);
```

**`App.tsx`**：同上替换 dialog/opener 调用

---

### Sidecar 端：stdin EOF 自杀（双向守护）

> 防止 Electron 主进程崩溃后 sidecar 变成孤儿进程。

**C#（`dotnet/civ-doc/Server/JsonRpcServer.cs`）**：
读取循环检测 `ReadLine() == null`（stdin EOF），立即 `Environment.Exit(0)`：
```csharp
while (true) {
    var line = await reader.ReadLineAsync();
    if (line is null) {
        // stdin 关闭，父进程已退出，自杀
        Environment.Exit(0);
        return;
    }
    // 正常处理...
}
```

**Python（`src/civ_core/api/server.py` 或 `__main__.py`）**：
stdin 读取异常或 EOFError 时退出：
```python
try:
    async for line in stdin:
        ...
except (EOFError, BrokenPipeError):
    sys.exit(0)
```

---

### package.json + vite 配置

移除：`@tauri-apps/plugin-dialog`、`@tauri-apps/plugin-opener`、`@tauri-apps/api`、`@tauri-apps/cli`

新增：`electron`、`electron-builder`、`vite-plugin-electron`、`vite-plugin-electron-renderer`

`vite.config.ts` 加插件：
```typescript
import electron from 'vite-plugin-electron';
electron([
  { entry: 'electron/main.ts' },
  { entry: 'electron/preload.ts', onstart: o => o.reload() },
])
```

### 删除

`frontend/src-tauri/` 整目录

### 文档同步

- `CLAUDE.md`：架构图更新（Tauri → Electron，invoke → ipc.rpc，civ-file:// 协议说明）
- `.ai/RULES.md`：目录结构（src-tauri → electron/）、测试命令（删 Rust cargo）、T6 打包（Tauri externalBin → electron-builder extraResources + app.isPackaged 分支）
- `frontend/CLAUDE.md`：构建命令（tauri:dev → npm run dev）

---

## 第二阶段：富格式 Excel 预览

### C# 新增：`xlsx.preview_rich`

**文件**：`dotnet/civ-doc/Handlers/XlsxHandlers.cs`

入参：`{ path, sheet?, max_rows? }`（默认 200）

**稀疏输出原则**（防止超大 JSON）：仅输出有内容或有非默认样式的单元格；`col_widths`/`row_heights` 仅输出非默认宽度/高度的行列；前端渲染时对坐标空缺处补空格即可。

返回（TypeScript 类型存 `frontend/src/components/viewers/excel-types.ts`）：
```typescript
export interface RichPreviewData {
  sheets: string[];
  sheet: string;
  total_rows: number;
  shown_rows: number;
  col_count: number;
  col_widths: Record<number, number>;   // 1-based，仅含自定义宽度的列
  row_heights: Record<number, number>;  // 1-based，仅含自定义高度的行
  merges: Array<{ sr: number; sc: number; er: number; ec: number }>; // 0-based
  cells: Array<{              // 稀疏：仅有值或有非默认样式的格
    r: number; c: number;    // 0-based
    v: string | number | boolean | null;
    d: string;               // 显示字符串
    bold?: true; italic?: true;
    ha?: 'l' | 'c' | 'r';
    bg?: string; fc?: string;  // "#RRGGBB"，仅在非默认时输出
    wrap?: true;
  }>;
  images: Array<{ r: number; c: number; data: string }>;  // base64 data URI
}
```

ClosedXML：`ws.MergedRanges` / `cell.Style.*` / `ws.Pictures`（整块 try-catch，失败返空）

主题色（`XLColorType.Theme`）：返回 null，前端按无填充处理。

### 前端 ExcelViewer

**`frontend/src/components/viewers/ExcelViewer.tsx`**

Props：`data`, `loading`, `highlightCols`, `highlightRows`, `onColClick(col: number)`, `onRowClick(row: number)`

核心：预计算 `suppressedSet`（合并覆盖格）+ `mergeMap`（主格 → rowSpan/colSpan），渲染时跳过 suppressed，主格加 span 属性。

集成 `data_processing`：`onColClick` → `setBatchIdCol`，`onRowClick` → `setHeaderRow`

---

## 第三阶段：PDF 渲染（流式，无 IPC Buffer）

### 前端 PdfViewer

**新增依赖**：`pdfjs-dist`

**`frontend/src/components/viewers/PdfViewer.tsx`**

```typescript
import { civFileUrl } from '../../lib/ipc';

// 加载：直接传 civ-file:// URL 给 pdfjs，由 pdfjs 按需发 Range 请求
// 不走 IPC Buffer，无内存暴涨，无卡顿
const task = pdfjsLib.getDocument(civFileUrl(pdfPath));

// Worker（Vite ?url 导入，sandbox: true 兼容）
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
```

渲染：canvas 逐页 + Intersection Observer 惰性加载（进视口前 200px 开始渲染）。

集成：
- `pdf_tools/Page.tsx`：点击文件行展开折叠式 PdfViewer
- `word2pdf/Page.tsx`：转换完成后展示输出文件预览

---

## 关键文件

| 文件 | 变更 |
|------|------|
| `frontend/electron/protocol.ts` | 新建（协议类型 + `civFileUrl` 工具函数） |
| `frontend/electron/sidecar.ts` | 新建（并发 transport，优雅 kill） |
| `frontend/electron/router.ts` | 新建（可注册路由） |
| `frontend/electron/main.ts` | 新建（孤儿防护 + isPackaged + civ-file 协议 + 沙盒） |
| `frontend/electron/preload.ts` | 新建（命名空间 IPC，无 fs） |
| `frontend/src/electron.d.ts` | 新建（类型声明） |
| `frontend/src/lib/ipc.ts` | 新建（前端唯一 IPC 出口 + civFileUrl） |
| `frontend/src/lib/rpc.ts` | 改为 `export const rpc = ipc.rpc` |
| `frontend/src/lib/shell.ts` | 改 opener → `ipc.shell.openPath` |
| `frontend/src/components/TitleBar.tsx` | CSS drag + `ipc.window.*` |
| `frontend/src/tools/*/Page.tsx` | `ipc.dialog.*` + `ipc.shell.openPath`（4 个文件） |
| `frontend/src/tools/*/SettingsForm.tsx` | 同上（涉及 dialog/opener 的文件） |
| `frontend/src/App.tsx` | 同上（dialog 调用） |
| `frontend/vite.config.ts` | 加 vite-plugin-electron |
| `frontend/package.json` | 换依赖 + scripts |
| `frontend/src-tauri/` | **整目录删除** |
| `CLAUDE.md` | 架构图更新 |
| `.ai/RULES.md` | 目录/命令/技术债更新 |
| `frontend/CLAUDE.md` | 构建命令更新 |
| `dotnet/civ-doc/Server/JsonRpcServer.cs` | ReadLine null 检测 + Environment.Exit(0) |
| `src/civ_core/api/server.py` 或 `__main__.py` | stdin EOF → sys.exit(0) |
| `dotnet/civ-doc/Handlers/XlsxHandlers.cs` | 新增 `xlsx.preview_rich`（稀疏输出） |
| `frontend/src/components/viewers/excel-types.ts` | 新建 |
| `frontend/src/components/viewers/ExcelViewer.tsx` | 新建 |
| `frontend/src/components/viewers/PdfViewer.tsx` | 新建（civFileUrl，无 readBytes） |
| `frontend/src/tools/data_processing/controller.tsx` | 新增 richPreview |
| `frontend/src/tools/data_processing/Page.tsx` | 替换预览组件 |
| `frontend/src/tools/pdf_tools/Page.tsx` | 加 PdfViewer |

## 验证

1. `cd frontend && npm install && npm run dev` → Electron 窗口正常启动，sandbox: true 无报错
2. 4 个工具页 RPC / dialog / opener 全功能正常
3. 强制结束 Electron 主进程 → dotnet / uv 子进程自动退出（无孤儿）
4. 含合并单元格 xlsx → ExcelViewer 正确渲染 rowspan/colspan，交互回调触发
5. 大 PDF 文件（> 10MB）→ PdfViewer 流式加载，无 UI 卡顿，内存平稳
6. 尝试用 civ-file:// 访问 workspace 外路径 → 403 Forbidden
7. `cd dotnet && dotnet test` 全过
8. `cd frontend && npx tsc -b --noEmit` 无报错（包括 electron/ 目录）
