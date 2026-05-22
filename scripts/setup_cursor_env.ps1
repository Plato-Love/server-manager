# Detect Cursor Agent CLI only (API key is read from dns_parse_config.json at runtime, not env)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ConfigPath = Join-Path $Root 'data\dns_parse_config.json'

function Find-AgentExe {
    $cmd = Get-Command agent -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.ps1'),
        (Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.exe'),
        (Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.cmd'),
        (Join-Path $env:USERPROFILE '.cursor\bin\agent.ps1')
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

Write-Host '=== Cursor Agent CLI ===' -ForegroundColor Cyan
$agent = Find-AgentExe
if ($agent) {
    Write-Host "Found: $agent" -ForegroundColor Green
    $agentDir = Split-Path $agent -Parent
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike "*$agentDir*") {
        [Environment]::SetEnvironmentVariable('Path', "$userPath;$agentDir", 'User')
        $env:Path = "$env:Path;$agentDir"
        Write-Host "Added to user PATH: $agentDir" -ForegroundColor Green
    }
} else {
    Write-Host 'agent not found, installing...' -ForegroundColor Yellow
    irm 'https://cursor.com/install?win32=true' | iex
    $agent = Find-AgentExe
    if ($agent) { Write-Host "Installed: $agent" -ForegroundColor Green }
    else { Write-Host 'Still not found. Restart terminal.' -ForegroundColor Red }
}

if (Test-Path $ConfigPath) {
    $cfg = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $key = "$($cfg.cursor_api_key)".Trim()
    if ($key) { Write-Host 'dns_parse_config.json: cursor_api_key is set (read at runtime by app)' -ForegroundColor Green }
    else { Write-Host "Edit cursor_api_key in: $ConfigPath" -ForegroundColor Yellow }
} else {
    Write-Host "Config missing: $ConfigPath" -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Note: API key is NOT stored in system env. App reads config file each time.' -ForegroundColor Gray
if ($agent) { & $agent --help 2>&1 | Select-Object -First 3 }
