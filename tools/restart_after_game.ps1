# Restart the bot (to pick up new code) as soon as the current game finishes.
# The supervisor (run_forever.ps1) relaunches it within ~15 s.
$log = Join-Path $PSScriptRoot "..\logs\bot.log"
$start = (Get-Item $log).Length
while ($true) {
    Start-Sleep 5
    $fs = [System.IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
    if ($fs.Length -lt $start) { $start = 0 }   # log rotated
    $fs.Seek($start, 'Begin') | Out-Null
    $new = (New-Object System.IO.StreamReader($fs)).ReadToEnd()
    $fs.Close()
    if ($new -match "RESULT") { break }
}
Start-Sleep 8   # let it reach the main menu
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'bot.py run' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
"$(Get-Date -Format s) restarted bot after game to load new code" | Add-Content (Join-Path $PSScriptRoot "..\logs\supervisor.log")
