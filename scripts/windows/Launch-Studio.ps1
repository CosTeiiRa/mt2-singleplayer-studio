param([switch]$NoBrowser, [switch]$NonInteractive)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Studio-Tools.ps1')
$studioPython = Get-StudioPython
if (-not (Test-Path -LiteralPath (Join-Path $studioProjectRoot 'data\studio-settings.json'))) {
    if ($NonInteractive) { throw 'Run Install Studio.bat first, or configure scripts/windows/Setup-Studio.ps1 -ServerRoot PATH -NoShortcut -NonInteractive.' }
    & (Join-Path $PSScriptRoot 'Setup-Studio.ps1')
}
$studioSettings = Get-StudioSettings $studioPython
$studioUrl = 'http://127.0.0.1:' + $studioSettings.port
$studioData = [string]$studioSettings.stateDir
New-Item -ItemType Directory -Path $studioData -Force | Out-Null
function Test-StudioReady {
    try { $studioResponse = Invoke-RestMethod -Uri "$studioUrl/api/bootstrap" -TimeoutSec 2 }
    catch { return $false }
    if ($studioResponse.application -ne 'metin2-server-studio' -or -not $studioResponse.root -or -not $studioResponse.stateDir) {
        throw ('Port ' + $studioSettings.port + ' belongs to another app or an older Studio. Close that instance or choose another port during setup.')
    }
    $sameRoot = ([IO.Path]::GetFullPath([string]$studioResponse.root) -ieq [IO.Path]::GetFullPath([string]$studioSettings.serverRoot))
    $sameState = $studioResponse.stateDir -and ([IO.Path]::GetFullPath([string]$studioResponse.stateDir) -ieq [IO.Path]::GetFullPath($studioData))
    $sameProject = $studioResponse.projectRoot -and ([IO.Path]::GetFullPath([string]$studioResponse.projectRoot) -ieq [IO.Path]::GetFullPath($studioProjectRoot))
    if ($studioResponse.application -ne 'metin2-server-studio' -or -not $sameRoot -or -not $sameState -or -not $sameProject) {
        throw ('Port ' + $studioSettings.port + ' already belongs to another Studio/world. Close that instance or choose another port in scripts/windows/Setup-Studio.ps1 -Port 8766.')
    }
    return $true
}
if (-not (Test-StudioReady)) {
    $studioScript = Join-Path $studioProjectRoot 'studio.py'
    $studioArguments = @('"' + $studioScript + '"', 'serve', '--root', '"' + $studioSettings.serverRoot + '"', '--port', [string]$studioSettings.port, '--state', '"' + $studioData + '"')
    $studioProcess = Start-Process -FilePath $studioPython -ArgumentList $studioArguments -WorkingDirectory $studioProjectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioData 'studio.out.log') -RedirectStandardError (Join-Path $studioData 'studio.err.log') -PassThru
    Set-Content -LiteralPath (Join-Path $studioData 'studio.pid') -Value $studioProcess.Id
    $studioReady = $false
    for ($studioAttempt = 0; $studioAttempt -lt 60; $studioAttempt++) {
        if (Test-StudioReady) { $studioReady = $true; break }
        $studioProcess.Refresh()
        if ($studioProcess.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $studioReady) { throw ('Studio could not start. Check ' + (Join-Path $studioData 'studio.err.log') + '. A busy port can be changed with Setup-Studio.ps1 -Port 8766.') }
}
if (-not $NoBrowser) { Start-Process $studioUrl }
Write-Host ('Metin2 Server Studio ' + $studioSettings.studioVersion + ' is running at ' + $studioUrl)
