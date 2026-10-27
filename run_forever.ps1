# Supervisor: keeps the bot running forever, unattended.
#  - restarts the bot whenever it exits (exit 3 = user stop via Ctrl+Alt+F8 or a STOP file)
#  - watchdog: kills the bot if its log/state has not changed for 10 minutes (hung)
#  - never starts, restarts or closes BTD6: the person at the PC keeps the game
#    open; while it is closed or not in front the bot pauses and waits for it
# Usage:  powershell -ExecutionPolicy Bypass -File run_forever.ps1
# -Hours is accepted but ignored: the scheduled task passed "-Hours 24", and
# the supervisor then stopped restarting the bot a day after it started (the
# bot sat idle from 2026-10-27 01:45). The supervisor now runs until a STOP
# file; the bot's own --hours 24 just makes it restart once a day.
param([double]$Hours = 0)

$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force logs | Out-Null
$sup = Join-Path $PSScriptRoot "logs\supervisor.log"
$botlog = Join-Path $PSScriptRoot "logs\bot.log"
$state = Join-Path $PSScriptRoot "logs\state.txt"
# Log a line. If supervisor.log stays locked by another program (an editor or
# a "tail" left open, OneDrive syncing), write to supervisor.fallback.log
# instead - before this fallback, a locked file silently lost every line.
$supFallback = Join-Path $PSScriptRoot "logs\supervisor.fallback.log"
function Note($m) {
    $line = "$(Get-Date -Format s) $m"
    $why = ""
    for ($i = 0; $i -lt 5; $i++) {
        try { Add-Content -Path $sup -Value $line -ErrorAction Stop; return } catch { $why = $_.Exception.Message; Start-Sleep -Milliseconds 300 }
    }
    # say why the main log refused the line: supervisor.log was found unlocked
    # while lines were still missing, so the cause is not known yet
    try { Add-Content -Path $supFallback -Value "$line   [supervisor.log: $why]" -ErrorAction Stop } catch { }
}
function LastChange {
    $t = [datetime]::MinValue
    foreach ($f in @($botlog, $state)) { if (Test-Path $f) { $w = (Get-Item $f).LastWriteTime; if ($w -gt $t) { $t = $w } } }
    return $t
}
function Results { if (Test-Path $botlog) { (Select-String -Path $botlog -Pattern "RESULT" -SimpleMatch | Measure-Object).Count } else { 0 } }

while ($true) {
    if (Test-Path (Join-Path $PSScriptRoot "STOP")) { Note "STOP file present - supervisor exiting"; break }
    # on-screen status strip (single instance, click-through)
    Start-Process -FilePath ($py -replace 'python\.exe$', 'pythonw.exe') -ArgumentList "tools\overlay.py" -WorkingDirectory $PSScriptRoot
    # rolling screen recording + daily highlight videos (single instance; NO_RECORD file turns it off)
    Start-Process -FilePath ($py -replace 'python\.exe$', 'pythonw.exe') -ArgumentList "-m", "btd6bot.recorder" -WorkingDirectory $PSScriptRoot
    $before = Results
    $p = Start-Process -FilePath $py -ArgumentList "bot.py", "run", "--hours", "24" -WorkingDirectory $PSScriptRoot -PassThru -WindowStyle Hidden
    while (-not $p.HasExited) {
        Start-Sleep 30
        if (((Get-Date) - (LastChange)).TotalMinutes -gt 10) {
            Note "watchdog: no log activity for 10 min - killing hung bot (pid $($p.Id))"
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            break
        }
        # A bot can keep writing log lines while making no progress: on
        # 2026-10-22 it clicked the same screen for 4.7 hours. state.txt is
        # refreshed every round in a game and every 2 minutes while idle, so
        # a stale one means a loop: restart the bot (never the game).
        if ((Test-Path $state) -and ((Get-Date) - (Get-Item $state).LastWriteTime).TotalMinutes -gt 25) {
            Note "watchdog: status unchanged for 25 min while the log runs - stuck in a loop; restarting the bot"
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            Start-Sleep 10
            break
        }
    }
    $p.WaitForExit()
    $code = $p.ExitCode
    Note "bot exited with code $code"
    if ($code -eq 3) { break }        # user stop
    if ($code -eq 5) { Start-Sleep 60; continue }   # another instance is running
    if ($code -eq 4) { continue }     # reload for new code: right away
    Start-Sleep 15
}
