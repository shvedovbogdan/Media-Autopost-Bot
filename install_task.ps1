$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$TaskName = "TG_Media_Autopost_Bot"
$TaskPath = "\TelegramBots\"
$Launcher = Join-Path $ProjectRoot "server_start.bat"

if (-not (Test-Path $Launcher)) {
    throw "server_start.bat not found: $Launcher"
}

$ScheduleService = New-Object -ComObject "Schedule.Service"
$ScheduleService.Connect()
$ScheduleRoot = $ScheduleService.GetFolder("\")
try {
    $null = $ScheduleService.GetFolder($TaskPath.TrimEnd("\"))
}
catch {
    $null = $ScheduleRoot.CreateFolder($TaskPath.Trim("\"))
}

$Arguments = '/d /c ""' + $Launcher + '""'
$Action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath

Write-Host "Created and started: $TaskPath$TaskName"
