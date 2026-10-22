# Supervisor: keeps the bot running forever, unattended.
#  - restarts the bot whenever it exits (exit 3 = user stop via Ctrl+Alt+F8 or a STOP file)
#  - watchdog: kills the bot if its log/state has not changed for 10 minutes (hung)
#  - after 2 exits in a row without a finished game, restarts BTD6 itself
#  - starts BTD6 through Steam whenever it is not running
# Usage:  powershell -ExecutionPolicy Bypass -File run_forever.ps1
param([double]$Hours = 0)   # 0 = forever

$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force logs | Out-Null
$sup = Join-Path $PSScriptRoot "logs\supervisor.log"
$botlog = Join-Path $PSScriptRoot "logs\bot.log"
$state = Join-Path $PSScriptRoot "logs\state.txt"
function Note($m) {
    for ($i = 0; $i -lt 5; $i++) {
        try { Add-Content -Path $sup -Value "$(Get-Date -Format s) $m" -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 300 }
    }
}
function LastChange {
    $t = [datetime]::MinValue
    foreach ($f in @($botlog, $state)) { if (Test-Path $f) { $w = (Get-Item $f).LastWriteTime; if ($w -gt $t) { $t = $w } } }
    return $t
}
function Results { if (Test-Path $botlog) { (Select-String -Path $botlog -Pattern "RESULT" -SimpleMatch | Measure-Object).Count } else { 0 } }

$deadline = if ($Hours -gt 0) { (Get-Date).AddHours($Hours) } else { [datetime]::MaxValue }
$noResult = 0
while ((Get-Date) -lt $deadline) {
    if (Test-Path (Join-Path $PSScriptRoot "STOP")) { Note "STOP file present - supervisor exiting"; break }
    if (-not (Get-Process BloonsTD6 -ErrorAction SilentlyContinue)) {
        Note "starting BTD6"
        Start-Process "steam://rungameid/960090"
        Start-Sleep 75
    }
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
    }
    $p.WaitForExit()
    $code = $p.ExitCode
    Note "bot exited with code $code"
    if ($code -eq 3) { break }        # user stop
    if ($code -eq 5) { Start-Sleep 60; continue }   # another instance is running
    if ((Results) -gt $before) { $noResult = 0 } elseif ($code -ne 4) { $noResult++ }
    if ($noResult -ge 2) {
        Note "2 exits without a finished game - restarting BTD6"
        Stop-Process -Name BloonsTD6 -Force -ErrorAction SilentlyContinue
        Start-Sleep 10
        $noResult = 0
    }
    if ($code -eq 4) { continue }     # reload for new code: right away
    Start-Sleep 15
}
