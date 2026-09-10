# civ-core Windows 开发环境一键配置
# 用法（仓库根目录）：
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# 会安装/配置：
#   .NET 9 SDK、Node.js LTS、Rust stable-msvc、uv、Python 3.12、
#   Microsoft C++ Build Tools（Desktop development with C++）、WebView2，
#   并恢复 Python / frontend / MCP / .NET / Rust 依赖。

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $extra = @(
        "$env:USERPROFILE\.cargo\bin",
        "$env:USERPROFILE\.local\bin"
    ) -join ";"
    $env:Path = "$machinePath;$userPath;$extra"
}

function Has-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-WingetInstall([string]$Id, [string]$Override = "") {
    Write-Step "安装/确认 $Id"
    $args = @(
        "install", "--id", $Id, "-e", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity"
    )
    if ($Override) {
        $args += @("--override", $Override)
    }

    & winget @args
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet 安装失败：$Id（退出码 $LASTEXITCODE）"
    }
    Refresh-Path
}

# Visual Studio Build Tools / .NET SDK 等安装需要管理员权限。
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "需要管理员权限，正在请求 UAC..." -ForegroundColor Yellow
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`""
    )
    Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -WorkingDirectory (Get-Location)
    exit 0
}

$RepoRoot = Split-Path -Parent $PSCommandPath
Set-Location $RepoRoot
$VsConfig = Join-Path $RepoRoot ".vsconfig"

Write-Host "========================================" -ForegroundColor DarkGray
Write-Host " civ-core Windows 开发环境配置" -ForegroundColor Green
Write-Host " 仓库：$RepoRoot"
Write-Host "========================================" -ForegroundColor DarkGray

if (-not (Has-Command "winget")) {
    throw "未找到 winget。请先在 Microsoft Store 安装/更新“应用安装程序 (App Installer)”。"
}

# 1) .NET 9 SDK
$hasDotnet9 = $false
if (Has-Command "dotnet") {
    $sdks = @(& dotnet --list-sdks 2>$null)
    $hasDotnet9 = [bool]($sdks | Where-Object { $_ -match '^9\.' })
}
if (-not $hasDotnet9) {
    Invoke-WingetInstall "Microsoft.DotNet.SDK.9"
} else {
    Write-Host "[OK] .NET 9 SDK 已安装" -ForegroundColor Green
}

# 2) Node.js >= 20；直接使用当前 LTS，避免 Vite/Tauri 被旧 Node 卡住。
$needNode = $true
if (Has-Command "node") {
    $nodeVersion = (& node --version).TrimStart('v')
    $nodeMajor = [int]($nodeVersion.Split('.')[0])
    if ($nodeMajor -ge 20) {
        $needNode = $false
        Write-Host "[OK] Node.js v$nodeVersion" -ForegroundColor Green
    }
}
if ($needNode) {
    Invoke-WingetInstall "OpenJS.NodeJS.LTS"
}

# 3) uv（负责 Python 3.12 + Python 依赖）
if (-not (Has-Command "uv")) {
    Invoke-WingetInstall "astral-sh.uv"
} else {
    Write-Host "[OK] $(& uv --version)" -ForegroundColor Green
}

# 4) Rust
if (-not (Has-Command "rustup")) {
    Invoke-WingetInstall "Rustlang.Rustup"
}
Refresh-Path
if (-not (Has-Command "rustup")) {
    throw "rustup 已安装但当前进程仍找不到。请关闭终端后重新运行 setup.ps1。"
}
Write-Step "配置 Rust stable-msvc"
& rustup default stable-msvc
if ($LASTEXITCODE -ne 0) { throw "Rust toolchain 配置失败" }
& rustup component add rustfmt clippy
if ($LASTEXITCODE -ne 0) { throw "Rust 组件安装失败" }
Refresh-Path

# 5) Tauri Windows 原生编译依赖：Microsoft C++ Build Tools
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vssetup = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"

function Find-VcToolsInstance {
    if (-not (Test-Path $vswhere)) { return $null }
    $path = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -eq 0 -and $path) { return ($path | Select-Object -First 1) }
    return $null
}

$vcInstance = Find-VcToolsInstance
if (-not $vcInstance) {
    Write-Step "安装/补齐 Microsoft C++ Build Tools"

    $existingVs = $null
    if (Test-Path $vswhere) {
        $existingVs = & $vswhere -latest -products * -property installationPath
        if ($existingVs) { $existingVs = $existingVs | Select-Object -First 1 }
    }

    if ($existingVs -and (Test-Path $vssetup)) {
        Write-Host "检测到现有 Visual Studio/Build Tools，追加 Desktop development with C++ 工作负载..."
        & $vssetup modify --installPath $existingVs --config $VsConfig --includeRecommended --passive --norestart
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3010) {
            throw "Visual Studio C++ 工作负载配置失败（退出码 $LASTEXITCODE）"
        }
    } else {
        $override = "--passive --wait --norestart --includeRecommended --config `"$VsConfig`""
        try {
            Invoke-WingetInstall "Microsoft.VisualStudio.BuildTools" $override
        } catch {
            # 部分 WinGet 源仍只暴露 2022 的固定 ID，保留回退。
            Write-Host "通用 Build Tools 包不可用，尝试 Visual Studio 2022 Build Tools..." -ForegroundColor Yellow
            Invoke-WingetInstall "Microsoft.VisualStudio.2022.BuildTools" $override
        }
    }

    $vcInstance = Find-VcToolsInstance
    if (-not $vcInstance) {
        Write-Warning "未能自动验证 MSVC x64/x86 组件。若 cargo 后续提示 linker 'link.exe' not found，请打开 Visual Studio Installer，确认已勾选“使用 C++ 的桌面开发”。"
    } else {
        Write-Host "[OK] C++ Build Tools: $vcInstance" -ForegroundColor Green
    }
} else {
    Write-Host "[OK] C++ Build Tools: $vcInstance" -ForegroundColor Green
}

# 6) WebView2。Windows 10 1803+ / Windows 11 通常已经自带；WinGet 会自动跳过已安装版本。
try {
    Invoke-WingetInstall "Microsoft.EdgeWebView2Runtime"
} catch {
    Write-Warning "WebView2 自动安装未完成。Windows 10 1803+ / Windows 11 通常已自带；若 Tauri 报 WebView2 缺失，再安装 Evergreen WebView2 Runtime。"
}

Refresh-Path

# 7) Python 3.12 + 锁定依赖
Write-Step "同步 Python 3.12 与 uv 依赖"
& uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 安装失败" }
& uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw "uv sync --frozen 失败" }

# 8) 前端依赖
Write-Step "恢复 frontend Node 依赖"
Push-Location (Join-Path $RepoRoot "frontend")
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "frontend npm ci 失败" }
} finally {
    Pop-Location
}

# 9) MCP server 依赖
if (Test-Path (Join-Path $RepoRoot "mcp\package-lock.json")) {
    Write-Step "恢复 MCP Node 依赖"
    Push-Location (Join-Path $RepoRoot "mcp")
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "mcp npm ci 失败" }
    } finally {
        Pop-Location
    }
}

# 10) C# restore/build
Write-Step "恢复并验证 C# sidecar"
$csharpProject = Join-Path $RepoRoot "dotnet\civ-doc\civ-doc.csproj"
& dotnet restore $csharpProject
if ($LASTEXITCODE -ne 0) { throw "dotnet restore 失败" }
& dotnet build $csharpProject --nologo --verbosity minimal --no-restore
if ($LASTEXITCODE -ne 0) { throw "dotnet build 失败" }

# 11) Rust 依赖预取
Write-Step "预取 Rust/Tauri 依赖"
Push-Location (Join-Path $RepoRoot "frontend\src-tauri")
try {
    & cargo fetch
    if ($LASTEXITCODE -ne 0) { throw "cargo fetch 失败" }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host " 环境配置完成" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host (".NET : " + (& dotnet --version))
Write-Host ("Node : " + (& node --version))
Write-Host ("npm  : " + (& npm.cmd --version))
Write-Host ("Rust : " + (& rustc --version))
Write-Host ("Cargo: " + (& cargo --version))
Write-Host ("uv   : " + (& uv --version))
Write-Host ("Python: " + (& uv run python --version))
Write-Host ""
Write-Host "现在可启动：" -ForegroundColor Cyan
Write-Host "  bash run.sh"
Write-Host ""
Write-Host "如果刚安装/修改了 Visual Studio Build Tools，首次启动前重开一次 VS Code 最稳。"
