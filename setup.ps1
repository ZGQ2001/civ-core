# civ-core Windows development environment bootstrap
# Run from repository root:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# This file intentionally uses ASCII only.
# Windows PowerShell 5.1 may parse UTF-8 files without BOM using the system ANSI
# code page, which can corrupt non-ASCII strings and even break PowerShell syntax.

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
    Write-Step "Install/check $Id"

    $args = @(
        "install", "--id", $Id, "-e", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity"
    )

    if ($Override) {
        $args += @("--override", $Override)
    }

    & winget @args
    $exitCode = $LASTEXITCODE

    # WinGet may use non-zero success-like codes for already-installed packages.
    # Re-check the command/package after installation where possible instead of
    # blindly assuming every non-zero code means the environment is unusable.
    if ($exitCode -ne 0) {
        throw "WinGet failed for $Id (exit code $exitCode)."
    }

    Refresh-Path
}

function Get-NodeMajor {
    if (-not (Has-Command "node")) { return 0 }
    $version = (& node --version).TrimStart('v')
    if (-not $version) { return 0 }
    return [int]($version.Split('.')[0])
}

# Some packages below require elevation. Relaunch this script as Administrator.
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Administrator privileges are required. Requesting UAC..." -ForegroundColor Yellow
    $argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argLine -WorkingDirectory (Get-Location).Path
    exit 0
}

$RepoRoot = Split-Path -Parent $PSCommandPath
Set-Location $RepoRoot
$VsConfig = Join-Path $RepoRoot ".vsconfig"

Write-Host "========================================" -ForegroundColor DarkGray
Write-Host " civ-core Windows environment setup" -ForegroundColor Green
Write-Host " repo: $RepoRoot"
Write-Host "========================================" -ForegroundColor DarkGray

if (-not (Has-Command "winget")) {
    throw "winget was not found. Install/update App Installer from Microsoft Store, then rerun setup.ps1."
}

# 1) .NET 9 SDK
$hasDotnet9 = $false
if (Has-Command "dotnet") {
    $sdks = @(& dotnet --list-sdks 2>$null)
    $hasDotnet9 = [bool]($sdks | Where-Object { $_ -match '^9\.' })
}

if (-not $hasDotnet9) {
    Invoke-WingetInstall "Microsoft.DotNet.SDK.9"
    Refresh-Path
} else {
    Write-Host "[OK] .NET 9 SDK" -ForegroundColor Green
}

# 2) Node.js 20+
$nodeMajor = Get-NodeMajor
if ($nodeMajor -lt 20) {
    Invoke-WingetInstall "OpenJS.NodeJS.LTS"
    Refresh-Path
    $nodeMajor = Get-NodeMajor
    if ($nodeMajor -lt 20) {
        throw "Node.js 20+ is required but was not detected after installation. Restart the terminal and rerun setup.ps1."
    }
} else {
    Write-Host "[OK] Node.js $(& node --version)" -ForegroundColor Green
}

# 3) uv
if (-not (Has-Command "uv")) {
    Invoke-WingetInstall "astral-sh.uv"
    Refresh-Path
}
if (-not (Has-Command "uv")) {
    throw "uv was installed but is not on PATH. Restart the terminal and rerun setup.ps1."
}
Write-Host "[OK] $(& uv --version)" -ForegroundColor Green

# 4) Rust stable MSVC toolchain
if (-not (Has-Command "rustup")) {
    Invoke-WingetInstall "Rustlang.Rustup"
    Refresh-Path
}
if (-not (Has-Command "rustup")) {
    throw "rustup was installed but is not on PATH. Restart the terminal and rerun setup.ps1."
}

Write-Step "Configure Rust stable-msvc"
& rustup default stable-msvc
if ($LASTEXITCODE -ne 0) { throw "rustup default stable-msvc failed." }
& rustup component add rustfmt clippy
if ($LASTEXITCODE -ne 0) { throw "Installing rustfmt/clippy failed." }
Refresh-Path

# 5) Microsoft C++ Build Tools for Tauri/MSVC
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vssetup = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\setup.exe"

function Find-VcToolsInstance {
    if (-not (Test-Path $vswhere)) { return $null }
    $path = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -eq 0 -and $path) {
        return ($path | Select-Object -First 1)
    }
    return $null
}

$vcInstance = Find-VcToolsInstance
if (-not $vcInstance) {
    Write-Step "Install/check Microsoft C++ Build Tools"

    $existingVs = $null
    if (Test-Path $vswhere) {
        $existingVs = & $vswhere -latest -products * -property installationPath
        if ($existingVs) { $existingVs = $existingVs | Select-Object -First 1 }
    }

    if ($existingVs -and (Test-Path $vssetup) -and (Test-Path $VsConfig)) {
        Write-Host "Existing Visual Studio detected. Adding C++ workload..."
        & $vssetup modify --installPath $existingVs --config $VsConfig --includeRecommended --passive --norestart
        $vsExit = $LASTEXITCODE
        if ($vsExit -ne 0 -and $vsExit -ne 3010) {
            throw "Visual Studio workload modification failed (exit code $vsExit)."
        }
    } else {
        $override = "--passive --wait --norestart --includeRecommended"
        if (Test-Path $VsConfig) {
            $override += " --config `"$VsConfig`""
        }

        $installed = $false
        foreach ($packageId in @("Microsoft.VisualStudio.BuildTools", "Microsoft.VisualStudio.2022.BuildTools")) {
            try {
                Invoke-WingetInstall $packageId $override
                $installed = $true
                break
            } catch {
                Write-Host "Package $packageId was not installed; trying fallback..." -ForegroundColor Yellow
            }
        }

        if (-not $installed) {
            throw "Could not install Visual Studio Build Tools automatically. Install Desktop development with C++ in Visual Studio Installer, then rerun setup.ps1."
        }
    }

    $vcInstance = Find-VcToolsInstance
    if ($vcInstance) {
        Write-Host "[OK] C++ Build Tools: $vcInstance" -ForegroundColor Green
    } else {
        Write-Warning "Could not verify the MSVC x64/x86 component. If cargo later reports 'link.exe' not found, open Visual Studio Installer and install Desktop development with C++."
    }
} else {
    Write-Host "[OK] C++ Build Tools: $vcInstance" -ForegroundColor Green
}

# 6) WebView2. Modern Windows usually already has it.
try {
    Invoke-WingetInstall "Microsoft.EdgeWebView2Runtime"
} catch {
    Write-Warning "WebView2 installation/check was skipped or failed. Modern Windows usually includes it. If Tauri reports WebView2 missing, install the Evergreen WebView2 Runtime."
}

Refresh-Path

# 7) Python 3.12 and locked Python dependencies
Write-Step "Install/check Python 3.12 and sync uv environment"
& uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw "uv python install 3.12 failed." }
& uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw "uv sync --frozen failed." }

# 8) Frontend dependencies
Write-Step "Restore frontend Node dependencies"
Push-Location (Join-Path $RepoRoot "frontend")
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "frontend npm ci failed." }
} finally {
    Pop-Location
}

# 9) MCP dependencies
$mcpLock = Join-Path $RepoRoot "mcp\package-lock.json"
if (Test-Path $mcpLock) {
    Write-Step "Restore MCP Node dependencies"
    Push-Location (Join-Path $RepoRoot "mcp")
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "mcp npm ci failed." }
    } finally {
        Pop-Location
    }
}

# 10) C# restore/build
Write-Step "Restore and build C# sidecar"
$csharpProject = Join-Path $RepoRoot "dotnet\civ-doc\civ-doc.csproj"
& dotnet restore $csharpProject
if ($LASTEXITCODE -ne 0) { throw "dotnet restore failed." }
& dotnet build $csharpProject --nologo --verbosity minimal --no-restore
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed." }

# 11) Pre-fetch Rust/Tauri crates
Write-Step "Fetch Rust/Tauri dependencies"
Push-Location (Join-Path $RepoRoot "frontend\src-tauri")
try {
    & cargo fetch
    if ($LASTEXITCODE -ne 0) { throw "cargo fetch failed." }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host " Environment setup completed" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host (".NET  : " + (& dotnet --version))
Write-Host ("Node  : " + (& node --version))
Write-Host ("npm   : " + (& npm.cmd --version))
Write-Host ("Rust  : " + (& rustc --version))
Write-Host ("Cargo : " + (& cargo --version))
Write-Host ("uv    : " + (& uv --version))
Write-Host ("Python: " + (& uv run python --version))
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  bash run.sh"
Write-Host ""
Write-Host "If Visual Studio Build Tools were installed or modified, restart VS Code before the first run."
