# Commit all changes and push to origin (if configured).
# Usage: powershell -ExecutionPolicy Bypass -File tools\push.ps1 "commit message"
param([Parameter(Position = 0)][string]$Message)

$ErrorActionPreference = 'Stop'

$git = 'C:\Program Files\Git\cmd\git.exe'
if (-not (Test-Path $git)) {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Write-Error 'git not found'; exit 1 }
    $git = $cmd.Source
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = 'Update ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')
}

& $git add -A
$status = & $git status --porcelain
if ([string]::IsNullOrWhiteSpace(($status | Out-String))) {
    Write-Host 'Nothing to commit.'
} else {
    & $git commit -m $Message
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$remotes = & $git remote
if ($remotes -contains 'origin') {
    & $git push -u origin HEAD
    exit $LASTEXITCODE
} else {
    Write-Host 'No origin remote configured; skipping push.'
}
