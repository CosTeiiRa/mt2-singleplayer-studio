param([string]$StateDir)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Studio-Tools.ps1')
if (-not $StateDir) {
    $studioConfigPath = Join-Path $studioProjectRoot 'data\studio-settings.json'
    if (-not (Test-Path -LiteralPath $studioConfigPath)) { Write-Host 'Studio has not been configured here.'; return }
    $studioSettings = Get-Content -LiteralPath $studioConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($studioSettings.schema -ne 1 -or -not $studioSettings.stateDir) { throw 'The local Studio data path is missing. Use Stop-Studio.ps1 -StateDir PATH.' }
    $StateDir = [string]$studioSettings.stateDir
}
$studioRunFile = Join-Path $StateDir 'studio-run.json'
if (-not (Test-Path -LiteralPath $studioRunFile)) { Write-Host 'No running merged Studio is recorded. Your game is unaffected.'; return }
$studioRun = Get-Content -LiteralPath $studioRunFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($studioRun.url -notmatch '^http://127\.0\.0\.1:[0-9]{4,5}$') { throw 'Invalid local Studio address; nothing was stopped.' }
$studioResponse = Invoke-RestMethod -Uri ($studioRun.url + '/api/bootstrap') -TimeoutSec 5
$sameProject = $studioResponse.projectRoot -and ([IO.Path]::GetFullPath([string]$studioResponse.projectRoot) -ieq [IO.Path]::GetFullPath($studioProjectRoot))
$sameState = $studioResponse.stateDir -and ([IO.Path]::GetFullPath([string]$studioResponse.stateDir) -ieq [IO.Path]::GetFullPath($StateDir))
if ($studioResponse.application -ne 'metin2-server-studio' -or -not $sameProject -or -not $sameState -or -not $studioResponse.token) { throw 'The address belongs to another Studio instance; nothing was stopped.' }
$studioHeaders = @{ 'X-Studio-Token' = [string]$studioResponse.token }
Invoke-RestMethod -Uri ($studioRun.url + '/api/shutdown') -Method Post -Headers $studioHeaders -ContentType 'application/json' -Body '{}' -TimeoutSec 5 | Out-Null
$studioPidFile = Join-Path $StateDir 'studio.pid'
if (Test-Path -LiteralPath $studioPidFile) { Remove-Item -LiteralPath $studioPidFile }
Write-Host 'Shutdown requested for this Studio only. Your Metin2 server is unaffected.'
