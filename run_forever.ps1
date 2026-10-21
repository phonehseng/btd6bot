# Keeps the bot running unattended: restarts it if it exits for any reason other
# than F8 (exit code 3). Starts BTD6 through Steam if it is not running.
# Usage:  powershell -ExecutionPolicy Bypass -File run_forever.ps1 [-Hours 10]
param([double]$Hours = 10)

$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
Set-Location $PSScriptRoot
$deadline = (Get-Date).AddHours($Hours)
New-Item -ItemType Directory -Force logs | Out-Null

while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process BloonsTD6 -ErrorAction SilentlyContinue)) {
        "$(Get-Date -Format s) starting BTD6" | Add-Content logs\supervisor.log
        Start-Process "steam://rungameid/960090"
        Start-Sleep 60
    }
    $left = [math]::Max(0.1, ($deadline - (Get-Date)).TotalHours)
    & $py bot.py run --hours $left
    $code = $LASTEXITCODE
    "$(Get-Date -Format s) bot exited with code $code" | Add-Content logs\supervisor.log
    if ($code -eq 3) { break }   # F8 pressed: the user wants it stopped
    if ($code -eq 4) { continue }  # reloading new code: restart right away
    Start-Sleep 15
}
