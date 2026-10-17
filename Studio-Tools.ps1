$ErrorActionPreference = 'Stop'
function Get-StudioPython {
    foreach ($studioCommandName in @('py.exe','python.exe','python3.exe','python3')) {
        $studioCommand = Get-Command $studioCommandName -ErrorAction SilentlyContinue
        if (-not $studioCommand) { continue }
        $studioPrefix = @()
        if ($studioCommandName -eq 'py.exe') { $studioPrefix = @('-3') }
        try {
            $studioProbe = @(& $studioCommand.Source @studioPrefix -c 'import sys; assert sys.version_info >= (3, 10); print(sys.executable)' 2>$null)
            if ($LASTEXITCODE -eq 0 -and $studioProbe.Count) { return ([string]$studioProbe[-1]).Trim() }
        } catch { }
    }
    throw 'Python 3.10+ was not found. Install Python from https://www.python.org/downloads/windows/ with the launcher/PATH option, then run Install Studio.bat again.'
}
function Get-StudioSettings([string]$Python) {
    $studioSetup = Join-Path $PSScriptRoot 'setup_studio.py'
    $studioSettingsOutput = & $Python $studioSetup --check
    if ($LASTEXITCODE -ne 0) { throw 'Studio setup is missing or invalid. Run Install Studio.bat and choose the existing Serwer folder.' }
    return ($studioSettingsOutput | ConvertFrom-Json)
}
