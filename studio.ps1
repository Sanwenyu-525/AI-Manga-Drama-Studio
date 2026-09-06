#Requires -Version 5.1
<#
  studio.ps1 — AI Manga Drama Studio 前后端一键管理脚本

  用法：
    .\studio.ps1               交互菜单（启动 / 停止 / 重启 / 状态 / 日志 / 桌面端 / 退出）
    .\studio.ps1 start         启动前后端 + 桌面端（自动执行数据库迁移）
    .\studio.ps1 stop          停止前后端 + 桌面端
    .\studio.ps1 restart       重启前后端 + 桌面端
    .\studio.ps1 desktop       启动桌面端（Tauri 窗口；若后端/前端未运行会自动拉起）
    .\studio.ps1 status        查看运行状态
    .\studio.ps1 logs          查看日志（.studio\*.log）

  说明：
    - 后端 FastAPI：uv run uvicorn（backend 目录），端口 17820，--reload 热重载
    - 前端 Vite：npm run dev（frontend 目录），端口 17821
    - 桌面端 Tauri：npm run tauri dev（apps\desktop 目录），窗口加载 http://127.0.0.1:17821
    - 进程 PID 记录在 .studio\*.pid，日志在 .studio\*.log
    - stop 先按 PID 记录结束本脚本启动的进程；若端口仍被占用（手动启动或记录失效），会强制结束占用进程以释放端口
#>

[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "restart", "desktop", "status", "logs")]
    [string]$Action = ""
)

$ErrorActionPreference = "Stop"

# ---- 配置 ----
$Root         = $PSScriptRoot
$StateDir     = Join-Path $Root ".studio"
$BackendDir   = Join-Path $Root "backend"
$FrontendDir  = Join-Path $Root "frontend"
$DesktopDir   = Join-Path $Root "apps\desktop"
$BackendPid   = Join-Path $StateDir "backend.pid"
$FrontendPid  = Join-Path $StateDir "frontend.pid"
$DesktopPid   = Join-Path $StateDir "desktop.pid"
$BackendLog   = Join-Path $StateDir "backend.log"
$FrontendLog  = Join-Path $StateDir "frontend.log"
$DesktopLog   = Join-Path $StateDir "desktop.log"
$BackendPort  = 17820
$FrontendPort = 17821

# ---- 基础工具 ----

function Ensure-StateDir {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
}

function Read-PidFile([string]$file) {
    if (Test-Path $file) {
        $n = 0
        $raw = (Get-Content -Path $file -Raw).Trim()
        if ([int]::TryParse($raw, [ref]$n)) { return $n }
    }
    return $null
}

function Write-PidFile([string]$file, [int]$value) {
    Ensure-StateDir
    Set-Content -Path $file -Value $value -Encoding ASCII
}

function Test-PortListening([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

function Get-PortOwner([int]$port) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Test-PidAlive([int]$processId) {
    return [bool](Get-Process -Id $processId -ErrorAction SilentlyContinue)
}

# 与 Tauri 的检查一致：HTTP 可达才算前端就绪（TCP 监听 ≠ 能响应请求，避免 tauri dev 干等 180s 后失败）
function Test-HttpReady([int]$port, [int]$timeoutSeconds = 3) {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec $timeoutSeconds
        return $true
    }
    catch {
        return $false
    }
}

function Kill-ProcessTree([int]$processId) {
    if ($processId -gt 0 -and (Test-PidAlive $processId)) {
        Write-Host "  结束进程树 PID $processId ..."
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & taskkill.exe /PID $processId /T /F *> $null
            if ($LASTEXITCODE -ne 0) {
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            }
        } catch {}
        finally { $ErrorActionPreference = $oldEAP }
    }
}

# ---- 启动 ----

function Start-Backend {
    if (Test-PortListening $BackendPort) {
        Write-Warning "端口 $BackendPort 已被进程 $(Get-PortOwner $BackendPort) 占用，跳过后端启动（请先执行 stop）"
        return $false
    }

    Write-Host "[backend] 数据库迁移 (alembic upgrade head) ..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        # uv/alembic 把 INFO 日志写到 stderr；EAP=Stop 下 2>&1 会把 stderr 变成终止性错误（PS 5.1），
        # 因此迁移期间临时放宽，并把全部输出重定向到文件（不产生错误记录，避免红色噪音 / 影响退出码）。
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $migrationLog = Join-Path $StateDir "migration.log"
            & uv run alembic upgrade head *> $migrationLog
            if ($LASTEXITCODE -ne 0) {
                $tail = Get-Content $migrationLog -Tail 20 -ErrorAction SilentlyContinue
                throw "alembic upgrade head 失败 (exit $LASTEXITCODE)`n$tail"
            }
        }
        finally {
            $ErrorActionPreference = $oldEAP
        }
    }
    finally { Pop-Location }

    Write-Host "[backend] 启动 uvicorn http://127.0.0.1:$BackendPort (日志: $BackendLog) ..." -ForegroundColor Cyan
    # 单字符串命令行（cmd /d /s /c）：避免不同 PowerShell 版本对参数数组的拼接差异
    $cmdline = "uv run uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --reload >> `"$BackendLog`" 2>&1"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/d /s /c $cmdline" -WorkingDirectory $BackendDir -WindowStyle Hidden -PassThru
    Write-PidFile $BackendPid $proc.Id

    # 等待端口就绪（最多 10 秒）
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PortListening $BackendPort) {
            Write-Host "[backend] 启动成功 [OK]" -ForegroundColor Green
            return $true
        }
        if (-not (Test-PidAlive $proc.Id)) { break }
    }
    Write-Warning "[backend] 启动可能失败，请查看日志: $BackendLog"
    return $false
}

function Start-Frontend {
    if (Test-PortListening $FrontendPort) {
        Write-Warning "端口 $FrontendPort 已被进程 $(Get-PortOwner $FrontendPort) 占用，跳过前端启动（请先执行 stop）"
        return $false
    }

    Write-Host "[frontend] 启动 vite http://127.0.0.1:$FrontendPort (日志: $FrontendLog) ..." -ForegroundColor Cyan
    $cmdline = "npm run dev >> `"$FrontendLog`" 2>&1"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/d /s /c $cmdline" -WorkingDirectory $FrontendDir -WindowStyle Hidden -PassThru
    Write-PidFile $FrontendPid $proc.Id

    # 等待端口就绪（最多 10 秒）
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PortListening $FrontendPort) {
            Write-Host "[frontend] 启动成功 [OK]" -ForegroundColor Green
            return $true
        }
        if (-not (Test-PidAlive $proc.Id)) { break }
    }
    Write-Warning "[frontend] 启动可能失败，请查看日志: $FrontendLog"
    return $false
}

function Start-Desktop {
    $desktopId = Read-PidFile $DesktopPid
    if ($desktopId -and (Test-PidAlive $desktopId)) {
        Write-Warning "桌面端已在运行 (PID $desktopId)，跳过启动"
        return $false
    }
    # 兜底：即使 PID 记录失效，若桌面端窗口进程仍存活也不再重复启动
    if (Get-Process -Name "ai-manga-studio" -ErrorAction SilentlyContinue) {
        Write-Warning "桌面端窗口进程 ai-manga-studio 已在运行，跳过启动"
        return $false
    }

    # 依赖就绪：桌面端窗口加载 http://127.0.0.1:${FrontendPort}，Tauri 连不上会干等 180s 后放弃。
    # 菜单 4 单独使用时，若后端/前端未运行则自动拉起（start 流程中此时已运行，均为 no-op）。
    if (-not (Test-PortListening $BackendPort)) {
        Start-Backend | Out-Null
    }
    if (-not (Test-PortListening $FrontendPort)) {
        Start-Frontend | Out-Null
    }

    # 与 Tauri 的检查一致（HTTP 可达）；最多重试 20 秒，覆盖 vite 刚监听但尚未就绪的窗口期
    $frontendReady = $false
    for ($i = 0; $i -lt 10; $i++) {
        if (Test-HttpReady $FrontendPort) { $frontendReady = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $frontendReady) {
        Write-Host "[desktop] 前端 (:${FrontendPort}) 未就绪，桌面端无法启动。请先执行 stop 释放端口后重试；日志: $FrontendLog" -ForegroundColor Red
        return $false
    }

    Write-Host "[desktop] 启动 Tauri 桌面端 (首次编译可能需要几分钟, 日志: $DesktopLog) ..." -ForegroundColor Cyan
    $cmdline = "npm run tauri dev >> `"$DesktopLog`" 2>&1"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/d /s /c $cmdline" -WorkingDirectory $DesktopDir -WindowStyle Hidden -PassThru
    Write-PidFile $DesktopPid $proc.Id

    # 等待窗口进程出现（最多 90 秒；首次 cargo 编译较慢，超时后窗口稍后仍会弹出）
    for ($i = 0; $i -lt 180; $i++) {
        Start-Sleep -Milliseconds 500
        if (Get-Process -Name "ai-manga-studio" -ErrorAction SilentlyContinue) {
            Write-Host "[desktop] 桌面端窗口已启动 [OK]" -ForegroundColor Green
            return $true
        }
        if (-not (Test-PidAlive $proc.Id)) { break }
    }
    Write-Warning "[desktop] 桌面端可能仍在编译中，请稍候或查看日志: $DesktopLog"
    return $false
}

function Start-All {
    Write-Host ""
    Write-Host "=== 启动 AI Manga Drama Studio ===" -ForegroundColor Cyan
    $b = Start-Backend
    $f = Start-Frontend
    $d = Start-Desktop
    if ($b -and $f) {
        Write-Host ""
        Write-Host "前后端启动完成：" -ForegroundColor Green
        Write-Host "  前端   http://127.0.0.1:$FrontendPort" -ForegroundColor Green
        Write-Host "  后端   http://127.0.0.1:$BackendPort/docs" -ForegroundColor Green
        Write-Host "  健康   http://127.0.0.1:$BackendPort/api/v1/health" -ForegroundColor Green
        if ($d) {
            Write-Host "  桌面端 Tauri 窗口已打开（加载 http://127.0.0.1:$FrontendPort）" -ForegroundColor Green
        }
    }
}

# ---- 停止 ----

function Stop-All {
    Write-Host ""
    Write-Host "=== 停止 AI Manga Drama Studio ===" -ForegroundColor Yellow
    $bProcessId = Read-PidFile $BackendPid
    $fProcessId = Read-PidFile $FrontendPid
    $dProcessId = Read-PidFile $DesktopPid
    if ($bProcessId -or $fProcessId -or $dProcessId) {
        Write-Host "按 PID 记录结束进程树: 后端=$bProcessId 前端=$fProcessId 桌面端=$dProcessId"
    }
    Kill-ProcessTree $bProcessId
    Kill-ProcessTree $fProcessId
    Kill-ProcessTree $dProcessId

    # 桌面端兜底：窗口进程未被 PID 树覆盖时（记录失效 / 用户手动关闭了 cmd 根进程），按进程名结束
    Get-Process -Name "ai-manga-studio" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Warning "桌面端窗口进程 $($_.Id) 未被 PID 记录覆盖，强制结束"
        Kill-ProcessTree $_.Id
    }

    # 端口兜底：反复结束当前占用进程直到端口释放（覆盖脚本外启动 / PID 记录失效 / 深层或孤儿进程链），
    # 每端口最多 8 轮，确保 stop/restart 一定释放前后端端口。
    foreach ($port in @($BackendPort, $FrontendPort)) {
        for ($attempt = 0; $attempt -lt 8 -and (Test-PortListening $port); $attempt++) {
            $owner = Get-PortOwner $port
            Write-Warning "端口 $port 仍被进程 $owner 占用，强制结束其进程树（第 $($attempt + 1) 轮）"
            Kill-ProcessTree $owner
            Start-Sleep -Milliseconds 500
        }
    }
    Remove-Item $BackendPid, $FrontendPid, $DesktopPid -Force -ErrorAction SilentlyContinue

    foreach ($port in @($BackendPort, $FrontendPort)) {
        if (Test-PortListening $port) {
            Write-Warning "端口 $port 仍被进程 $(Get-PortOwner $port) 占用，请手动结束"
        }
    }
    Write-Host "已停止 [OK]" -ForegroundColor Green
}

function Restart-All {
    Stop-All
    Start-All
}

# ---- 状态 / 日志 ----

function Show-Status {
    Write-Host ""
    Write-Host "=== 运行状态 ===" -ForegroundColor Cyan
    foreach ($item in @(
        @{ Name = "后端 (uvicorn)"; Port = $BackendPort;  PidFile = $BackendPid },
        @{ Name = "前端 (vite)";   Port = $FrontendPort; PidFile = $FrontendPid },
        @{ Name = "桌面端 (tauri)"; Port = $null;        PidFile = $DesktopPid }
    )) {
        $processId = Read-PidFile $item.PidFile
        $listening = if ($item.Port) { Test-PortListening $item.Port } else { $false }
        $alive = ($processId -gt 0) -and (Test-PidAlive $processId)
        $status = if ($listening) {
            "运行中 (端口 $($item.Port))"
        } elseif ($alive -or (Get-Process -Name "ai-manga-studio" -ErrorAction SilentlyContinue)) {
            "运行中 (进程 $processId)"
        } else {
            "未运行"
        }
        Write-Host ("  {0,-16} {1}" -f $item.Name, $status)
    }
}

function Show-Logs {
    Write-Host ""
    Write-Host "=== 日志文件 ===" -ForegroundColor Cyan
    foreach ($log in @($BackendLog, $FrontendLog, $DesktopLog)) {
        if (Test-Path $log) {
            Write-Host ""
            Write-Host "----- $log (最后 15 行) -----" -ForegroundColor Cyan
            Get-Content -Path $log -Tail 15
        } else {
            Write-Host "  日志不存在: $log"
        }
    }
}

# ---- 交互菜单 ----

function Show-Menu {
    if (-not [Console]::IsOutputRedirected) {
        Clear-Host
    }
    Write-Host ""
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host "     AI Manga Drama Studio 管理脚本" -ForegroundColor Cyan
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "    1) 启动     (start)" -ForegroundColor White
    Write-Host "    2) 停止     (stop)" -ForegroundColor White
    Write-Host "    3) 重启     (restart)" -ForegroundColor White
    Write-Host "    4) 桌面端   (desktop)" -ForegroundColor White
    Write-Host "    5) 状态     (status)" -ForegroundColor White
    Write-Host "    6) 查看日志 (logs)" -ForegroundColor White
    Write-Host "    0) 退出" -ForegroundColor White
    Write-Host ""
}

function Enter-Menu {
    while ($true) {
        Show-Menu
        $choice = Read-Host "  请选择"
        switch ($choice) {
            { $_ -in @("1", "start") }     { Start-All }
            { $_ -in @("2", "stop") }      { Stop-All }
            { $_ -in @("3", "restart") }   { Restart-All }
            { $_ -in @("4", "desktop") }   { Start-Desktop }
            { $_ -in @("5", "status") }    { Show-Status }
            { $_ -in @("6", "logs") }      { Show-Logs }
            { $_ -in @("0", "exit", "quit", "q") } { Write-Host "再见！"; return }
            default { Write-Host "无效选项，请重新输入" -ForegroundColor Red }
        }
        Read-Host "`n  按回车键继续..." | Out-Null
    }
}

# ---- 入口 ----

if ($Action) {
    switch ($Action) {
        "start"   { Start-All }
        "stop"    { Stop-All }
        "restart" { Restart-All }
        "desktop" { Start-Desktop }
        "status"  { Show-Status }
        "logs"    { Show-Logs }
    }
}
else {
    Enter-Menu
}
