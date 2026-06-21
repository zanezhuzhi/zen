$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $ScriptDir "collect_daily_domains.py"

$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) {
    & py -3 $Script @args
} else {
    & python $Script @args
}
