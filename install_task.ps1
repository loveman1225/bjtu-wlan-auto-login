$ErrorActionPreference = "Stop"

$taskName = "CampusNetGuard"
$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $baseDir "CampusNetGuard.exe"
$scriptPath = Join-Path $baseDir "campus_net_guard.py"

if (Test-Path $exePath) {
  $execute = $exePath
  $argument = $null
} else {
  $execute = (Get-Command python).Source
  $argument = "`"$scriptPath`""
}

if ($null -eq $argument) {
  $action = New-ScheduledTaskAction -Execute $execute -WorkingDirectory $baseDir
} else {
  $action = New-ScheduledTaskAction -Execute $execute -Argument $argument -WorkingDirectory $baseDir
}
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
Write-Host "Program: $execute $argument"
