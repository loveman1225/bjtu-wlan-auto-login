$ErrorActionPreference = "Stop"

$taskName = "CampusNetGuard"
$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $baseDir "campus_net_guard.py"
$python = (Get-Command python).Source

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$scriptPath`"" -WorkingDirectory $baseDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 4)

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Check BJTU captive portal and open login page when web.wlan.bjtu needs authentication." `
  -Force | Out-Null

Write-Host "Installed scheduled task: $taskName"
Write-Host "Script: $scriptPath"
