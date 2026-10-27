# Turn the bot back on after bot_off.ps1 (or the HUD's OFF button): removes
# the STOP, HOLD and PAUSE files and starts the supervisor through the BTD6Bot
# scheduled task, the same way it starts at logon. The supervisor brings back
# the HUD overlay and the recorder. BTD6 must be open for the bot to play.
# Usage:  powershell -ExecutionPolicy Bypass -File tools\bot_on.ps1
$root = Split-Path $PSScriptRoot -Parent
foreach ($name in "STOP", "HOLD", "PAUSE") { Remove-Item (Join-Path $root $name) -ErrorAction SilentlyContinue }

$running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_forever\.ps1' -and $_.ProcessId -ne $PID }
if ($running) {
    Write-Host "The bot is already running."
} else {
    schtasks /run /tn BTD6Bot | Out-Null
    Write-Host "The BTD6 bot is starting. Keep BTD6 open; the HUD appears at the top of the screen."
}
Start-Sleep 3
