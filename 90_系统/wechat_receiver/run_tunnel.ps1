$ErrorActionPreference = "Stop"
$Cloudflared = "C:\软件\cloudflared\cloudflared.exe"
if (-not (Test-Path $Cloudflared)) {
    $Cloudflared = "cloudflared"
}

& $Cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
