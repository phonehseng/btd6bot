# Turn the bot off completely: the bot, its supervisor, the HUD overlay and
# the screen recorder. BTD6 itself is left open.
#
# It writes the STOP file, which every part of the bot watches and exits on
# by itself (a round's evidence and recordings are closed properly). Anything
# still running after 45 seconds is ended. The STOP file stays, so nothing
# starts the bot again - not the logon task, not the hourly caretaker - until
# bot_on.ps1 removes it.
# Usage:  powershell -ExecutionPolicy Bypass -File tools\bot_off.ps1
$root = Split-Path $PSScriptRoot -Parent
Set-Content -Path (Join-Path $root "STOP") -Value "$(Get-Date -Format s) turned off with bot_off.ps1"

# the bot's own processes, found by their command lines
function BotProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match 'bot\.py run|run_forever\.ps1|tools\\overlay\.py|btd6bot\.recorder|btd6bot_cache\\tools\\ffmpeg' -and
        $_.ProcessId -ne $PID
    }
}

Write-Host "Turning the BTD6 bot off..."
$deadline = (Get-Date).AddSeconds(45)
while ((BotProcesses) -and (Get-Date) -lt $deadline) { Start-Sleep 2 }
$left = @(BotProcesses)
foreach ($p in $left) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
if ($left.Count) { Write-Host "Ended $($left.Count) process(es) that did not exit on their own." }
Write-Host "The bot is off. Run 'BTD6 Bot ON' to start it again."
Start-Sleep 3
