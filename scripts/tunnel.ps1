# Cloudflare Tunnel Launcher for StemLab AI
$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " StemLab AI - Starting Cloudflare Tunnel          " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$cloudflaredPath = Join-Path $PSScriptRoot "..\cloudflared.exe"

if (-not (Test-Path $cloudflaredPath)) {
    Write-Host "Downloading cloudflared.exe..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cloudflaredPath
}

Write-Host "Exposing StemLab AI (http://localhost:3000) to the public internet..." -ForegroundColor Green
& $cloudflaredPath tunnel --url http://localhost:3000
