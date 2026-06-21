$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ScriptDir "start_feishu_inbox.ps1"
$RadarScript = Join-Path $ScriptDir "process_daily_inbox.ps1"
$ReceiverTaskName = "Zen Feishu Inbox Receiver"
$RadarTaskName = "Zen Daily Opportunity Radar"

if (-not (Test-Path $StartScript)) {
    throw "Missing start script: $StartScript"
}
if (-not (Test-Path $RadarScript)) {
    throw "Missing radar script: $RadarScript"
}

$ReceiverAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$EveryFiveMinutes = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$ReceiverSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $ReceiverTaskName `
    -Action $ReceiverAction `
    -Trigger $EveryFiveMinutes `
    -Settings $ReceiverSettings `
    -Force | Out-Null

$RadarAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RadarScript`""
$RadarTrigger = New-ScheduledTaskTrigger -Daily -At 21:30
$RadarSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $RadarTaskName `
    -Action $RadarAction `
    -Trigger $RadarTrigger `
    -Settings $RadarSettings `
    -Force | Out-Null

function New-PowerShellShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$Description
    )
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($Path)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = $Description
    $Shortcut.Save()
}

$Startup = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$StartupShortcutPath = Join-Path $Startup "启动飞书收件箱.lnk"
New-PowerShellShortcut `
    -Path $StartupShortcutPath `
    -ScriptPath $StartScript `
    -Description "Start the Zen Feishu inbox receiver at Windows login"

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "启动飞书收件箱.lnk"
New-PowerShellShortcut `
    -Path $ShortcutPath `
    -ScriptPath $StartScript `
    -Description "Start the Zen Feishu inbox receiver"

& $StartScript

Write-Host "Installed scheduled task: $ReceiverTaskName"
Write-Host "Installed scheduled task: $RadarTaskName"
Write-Host "Created startup shortcut: $StartupShortcutPath"
Write-Host "Created desktop shortcut: $ShortcutPath"
