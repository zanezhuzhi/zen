$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    py -3 -m venv (Join-Path $ScriptDir ".venv")
}

& $VenvPython (Join-Path $ScriptDir "app.py")
