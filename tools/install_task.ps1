# Registers the bot supervisor as a Windows scheduled task so it runs
# independently of any terminal session, and starts it at logon.
#   powershell -ExecutionPolicy Bypass -File tools\install_task.ps1        (install + start now)
#   schtasks /end /tn BTD6Bot ; schtasks /run /tn BTD6Bot                  (restart)
$root = Split-Path -Parent $PSScriptRoot
$ps = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction -Execute $ps -WorkingDirectory $root `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$root\run_forever.ps1`" -Hours 24"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName BTD6Bot -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName BTD6Bot
"BTD6Bot task installed and started"
