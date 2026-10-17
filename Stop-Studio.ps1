param([string]$StateDir)
$ErrorActionPreference = 'Stop'
if (-not $StateDir) {
    $studioConfigPath = Join-Path $PSScriptRoot 'data\studio-settings.json'
    if (-not (Test-Path -LiteralPath $studioConfigPath)) { Write-Host 'Studio has not been configured here.'; return }
    $studioSettings = Get-Content -LiteralPath $studioConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($studioSettings.schema -ne 1 -or -not $studioSettings.stateDir) { throw 'The local Studio data path is missing. Use Stop-Studio.ps1 -StateDir PATH.' }
    $StateDir = [string]$studioSettings.stateDir
}
$studioPidFile = Join-Path $StateDir 'studio.pid'
if (-not (Test-Path -LiteralPath $studioPidFile)) { Write-Host 'No Studio launcher process is recorded. Your game is unaffected.'; return }
$studioPid = [int](Get-Content -LiteralPath $studioPidFile)
$studioProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$studioPid" -ErrorAction SilentlyContinue
$studioScript = Join-Path $PSScriptRoot 'server.py'
if ($studioProcess -and $studioProcess.CommandLine -and $studioProcess.CommandLine.Contains($studioScript)) {
    Stop-Process -Id $studioPid
    Write-Host 'Studio closed. Your Metin2 server is unaffected.'
} elseif ($studioProcess) { throw 'The recorded process belongs to another application; nothing was stopped.' }
Remove-Item -LiteralPath $studioPidFile
