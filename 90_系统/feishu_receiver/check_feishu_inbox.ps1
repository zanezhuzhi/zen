$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppScript = Join-Path $ScriptDir "app.py"
$AppPattern = [regex]::Escape($AppScript)
$LogFile = Join-Path (Split-Path -Parent $ScriptDir) "logs\feishu_receiver.log"
$Today = Get-Date -Format "yyyy-MM-dd"
$InboxFile = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "00_入口收件箱\飞书同步\$Today.md"

$Processes = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match $AppPattern -and
            $_.Name -match "^python(\.exe)?$"
        }
)

[pscustomobject]@{
    Running = $Processes.Count -gt 0
    ProcessIds = ($Processes | Select-Object -ExpandProperty ProcessId) -join ", "
    LogFile = $LogFile
    TodayInbox = $InboxFile
    TodayInboxExists = Test-Path $InboxFile
} | Format-List

if (Test-Path $LogFile) {
    Write-Host ""
    Write-Host "Recent log:"
    Get-Content -Tail 20 -Encoding UTF8 $LogFile |
        ForEach-Object {
            $_ -replace 'access_key=[^&\s]+','access_key=***' -replace 'ticket=[^\]\s]+','ticket=***'
        }
}
