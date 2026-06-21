$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    py -3 -m venv (Join-Path $ScriptDir ".venv")
    & $Python -m pip install --upgrade pip lark-oapi python-dotenv
}

& $Python (Join-Path $ScriptDir "app.py")
