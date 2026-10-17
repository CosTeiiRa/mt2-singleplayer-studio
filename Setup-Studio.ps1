param(
    [string]$ServerRoot,
    [int]$Port = 0,
    [string]$StateDir,
    [switch]$NoShortcut,
    [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Studio-Tools.ps1')
$studioPython = Get-StudioPython
if (-not $ServerRoot) {
    if ($NonInteractive) { throw 'Provide -ServerRoot with the existing Serwer folder.' }
    Write-Host 'Metin2 Server Studio - connect your existing game'
    Write-Host 'Setup saves local Studio settings only. It does not change or restart your game.'
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $studioFolderPicker = New-Object System.Windows.Forms.FolderBrowserDialog
        $studioFolderPicker.Description = 'Select the Serwer folder inside your existing Metin2 Singleplayer installation.'
        $studioFolderPicker.ShowNewFolderButton = $false
        try {
            if ($studioFolderPicker.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $ServerRoot = $studioFolderPicker.SelectedPath }
        } finally { $studioFolderPicker.Dispose() }
    } catch { Write-Host 'Folder picker unavailable. You can paste the folder path below.' }
    if (-not $ServerRoot) { $ServerRoot = Read-Host 'Paste the full path to Serwer (or its Metin2 Singleplayer parent folder)' }
    if (-not $ServerRoot) { throw 'No server folder selected. No setup was changed.' }
}
$studioSetupArguments = @((Join-Path $PSScriptRoot 'setup_studio.py'), '--server-root', $ServerRoot)
if ($Port) { $studioSetupArguments += @('--port', [string]$Port) }
if ($StateDir) { $studioSetupArguments += @('--state', $StateDir) }
$studioSetupOutput = & $studioPython @studioSetupArguments
if ($LASTEXITCODE -ne 0) { throw 'The existing game could not be configured. Review the missing files above; setup does not download or replace the game.' }
$studioSettings = $studioSetupOutput | ConvertFrom-Json
if (-not $NoShortcut) { & (Join-Path $PSScriptRoot 'Create-DesktopShortcut.ps1') }
Write-Host ('Studio ' + $studioSettings.studioVersion + ' configured.')
Write-Host ('Game: ' + $studioSettings.serverRoot + ' (version ' + $studioSettings.serverVersion + ')')
Write-Host ('Local history and backups: ' + $studioSettings.stateDir)
Write-Host ('Open Start Studio.bat, or the desktop shortcut. Address: http://127.0.0.1:' + $studioSettings.port)
