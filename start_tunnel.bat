@echo off
title StemLab AI - Cloudflare Tunnel
echo Starting Cloudflare Tunnel for StemLab AI...
cloudflared.exe tunnel --url http://localhost:3000
pause
