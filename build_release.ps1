# 生产构建：在项目根目录 PowerShell 中执行 .\build_release.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Py) { throw '未找到 python，请将 Python 3.10+ 加入 PATH 或使用完整路径后重试' }

& $Py.Source -m pip install -r requirements-build.txt --quiet

if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

& $Py.Source -m PyInstaller server-manager.spec --noconfirm

Write-Host ""
Write-Host "完成。输出目录: $Root\\dist\\ServerManager\\ServerManager.exe" -ForegroundColor Green
