$ErrorActionPreference = "Stop"

$taskName = "CampusNetGuard"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Removed scheduled task: $taskName"
