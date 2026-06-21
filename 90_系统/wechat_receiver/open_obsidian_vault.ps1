$ErrorActionPreference = "Stop"
$Obsidian = "C:\软件\Obsidian\App\Obsidian.exe"
$Vault = "D:\==我的学习库=="

if (-not (Test-Path $Obsidian)) {
    throw "Obsidian not found: $Obsidian"
}

Start-Process -FilePath $Obsidian -ArgumentList @("open", "--path", $Vault)
