$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunScript = Join-Path $ScriptDir "run_feishu_receiver.ps1"
$AppScript = Join-Path $ScriptDir "app.py"
$LogDir = Join-Path (Split-Path -Parent $ScriptDir) "logs"
$OutLog = Join-Path $LogDir "feishu_receiver.stdout.log"
$ErrLog = Join-Path $LogDir "feishu_receiver.stderr.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-FeishuReceiverProcess {
    $AppPattern = [regex]::Escape($AppScript)
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match $AppPattern -and
            $_.Name -match "^python(\.exe)?$"
        }
}

$Existing = @(Get-FeishuReceiverProcess)
if ($Existing.Count -gt 0) {
    $Ids = ($Existing | Select-Object -ExpandProperty ProcessId) -join ", "
    Write-Host "Feishu inbox receiver is already running. PID: $Ids"
    exit 0
}

$Process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $RunScript) `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Start-Sleep -Seconds 3
$After = @(Get-FeishuReceiverProcess)
if ($After.Count -gt 0 -or -not $Process.HasExited) {
    Write-Host "Feishu inbox receiver started. Launcher PID: $($Process.Id)"
    exit 0
}

Write-Error "Feishu inbox receiver failed to start. Check $ErrLog"
