$ErrorActionPreference = "Stop"

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $baseDir "CampusNetGuard.exe"

if (-not (Test-Path $exePath)) {
  throw "CampusNetGuard.exe not found. Run .\build_exe.ps1 first."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell

function New-Shortcut {
  param(
    [string]$Name,
    [string]$Arguments,
    [string]$Description
  )

  $shortcutPath = Join-Path $desktop "$Name.lnk"
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $exePath
  $shortcut.Arguments = $Arguments
  $shortcut.WorkingDirectory = $baseDir
  $shortcut.Description = $Description
  $shortcut.IconLocation = "$exePath,0"
  $shortcut.Save()
  Write-Host "Created shortcut: $shortcutPath"
}

New-Shortcut `
  -Name "Campus Net Guard - Enable 5min" `
  -Arguments "--install-task --interval-minutes 5" `
  -Description "Install Campus Net Guard scheduled task to run every 5 minutes."

New-Shortcut `
  -Name "Campus Net Guard - Run Once" `
  -Arguments "" `
  -Description "Run Campus Net Guard once immediately."

New-Shortcut `
  -Name "Campus Net Guard - Disable" `
  -Arguments "--uninstall-task" `
  -Description "Remove the Campus Net Guard scheduled task."
