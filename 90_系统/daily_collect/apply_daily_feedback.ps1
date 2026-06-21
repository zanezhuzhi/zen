$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $ScriptDir "apply_daily_feedback.py"

$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) {
    & py -3 $Script @args
} else {
    & python $Script @args
}
