#Requires -Version 5.1
<#
  studio.ps1 — AI Manga Drama Studio 前后端一键管理脚本

  用法：
    .\studio.ps1               交互菜单（启动 / 停止 / 重启 / 状态 / 日志 / 退出）
    .\studio.ps1 start         启动前后端（自动执行数据库迁移）
    .\studio.ps1 stop          停止前后端
    .\studio.ps1 restart       重启前后端
    .\studio.ps1 status        查看运行状态
    .\studio.ps1 logs          查看前后端日志（.studio\*.log）

  说明：
    - 后端 FastAPI：uv run uvicorn（backend 目录），端口 17820，--reload 热重载
    - 前端 Vite：npm run dev（frontend 目录），端口 17821
    - 进程 PID 记录在 .studio\*.pid，日志在 .studio\*.log
    - stop 只结束本脚本启动的进程（按 PID 记录），不影响手动启动的服务
#>

[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "restart", "status", "logs")]
    [string]$Action = ""
)

$ErrorActionPreference = "Stop"

# ---- 配置 ----
$Root         = $PSScriptRoot
$StateDir     = Join-Path $Root ".studio"
$BackendDir   = Join-Path $Root "backend"
$FrontendDir  = Join-Path $Root "frontend"
$BackendPid   = Join-Path $StateDir "backend.pid"
$FrontendPid  = Join-Path $StateDir "frontend.pid"
$BackendLog   = Join-Path $StateDir "backend.log"
$FrontendLog  = Join-Path $StateDir "frontend.log"
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

function Kill-ProcessTree([int]$processId) {
    if ($processId -gt 0 -and (Test-PidAlive $processId)) {
        Write-Host "  结束进程树 PID $processId ..."
        # 2>&1 合并到成功流：2>$null 在 $ErrorActionPreference=Stop 下会把 stderr 变成终止性错误
        & taskkill.exe /PID $processId /T /F 2>&1 | Out-Null
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
        & uv run alembic upgrade head 2>&1 | Out-Host
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

function Start-All {
    Write-Host ""
    Write-Host "=== 启动 AI Manga Drama Studio ===" -ForegroundColor Cyan
    $b = Start-Backend
    $f = Start-Frontend
    if ($b -and $f) {
        Write-Host ""
        Write-Host "全部启动完成：" -ForegroundColor Green
        Write-Host "  前端   http://127.0.0.1:$FrontendPort" -ForegroundColor Green
        Write-Host "  后端   http://127.0.0.1:$BackendPort/docs" -ForegroundColor Green
        Write-Host "  健康   http://127.0.0.1:$BackendPort/api/v1/health" -ForegroundColor Green
    }
}

# ---- 停止 ----

function Stop-All {
    Write-Host ""
    Write-Host "=== 停止 AI Manga Drama Studio ===" -ForegroundColor Yellow
    $bProcessId = Read-PidFile $BackendPid
    $fProcessId = Read-PidFile $FrontendPid
    if (-not $bProcessId -and -not $fProcessId) {
        Write-Host "没有运行中的服务（无 PID 记录）"
    }
    Kill-ProcessTree $bProcessId
    Kill-ProcessTree $fProcessId
    Remove-Item $BackendPid, $FrontendPid -Force -ErrorAction SilentlyContinue

    Start-Sleep -Seconds 2
    foreach ($port in @($BackendPort, $FrontendPort)) {
        if (Test-PortListening $port) {
            Write-Warning "端口 $port 仍被进程 $(Get-PortOwner $port) 占用（可能是手动启动的残留），请手动结束"
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
        @{ Name = "前端 (vite)";   Port = $FrontendPort; PidFile = $FrontendPid }
    )) {
        $processId = Read-PidFile $item.PidFile
        $listening = Test-PortListening $item.Port
        $alive = ($processId -gt 0) -and (Test-PidAlive $processId)
        $status = if ($listening) {
            "运行中 (端口 $($item.Port))"
        } elseif ($alive) {
            "进程存活但端口未监听"
        } else {
            "未运行"
        }
        Write-Host ("  {0,-16} {1}" -f $item.Name, $status)
    }
}

function Show-Logs {
    Write-Host ""
    Write-Host "=== 日志文件 ===" -ForegroundColor Cyan
    foreach ($log in @($BackendLog, $FrontendLog)) {
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
    Write-Host "    4) 状态     (status)" -ForegroundColor White
    Write-Host "    5) 查看日志 (logs)" -ForegroundColor White
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
            { $_ -in @("4", "status") }    { Show-Status }
            { $_ -in @("5", "logs") }      { Show-Logs }
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
        "status"  { Show-Status }
        "logs"    { Show-Logs }
    }
}
else {
    Enter-Menu
}
