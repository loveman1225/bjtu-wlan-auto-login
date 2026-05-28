$ErrorActionPreference = "Stop"

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $baseDir

python -m PyInstaller --onefile --windowed --name CampusNetGuard .\campus_net_guard.py

Copy-Item .\dist\CampusNetGuard.exe .\CampusNetGuard.exe -Force

Write-Host "Built: $(Join-Path $baseDir 'CampusNetGuard.exe')"
