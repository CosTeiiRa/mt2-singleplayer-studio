param([string]$DesktopPath = [Environment]::GetFolderPath('Desktop'))
$ErrorActionPreference = 'Stop'
$studioLauncher = Join-Path $PSScriptRoot 'Launch-Studio.ps1'
if (-not (Test-Path -LiteralPath $studioLauncher)) { throw 'Studio launcher was not found.' }
if (-not (Test-Path -LiteralPath $DesktopPath -PathType Container)) { throw 'Desktop folder was not found.' }
$studioPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$studioArguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $studioLauncher + '"'
$studioShell = New-Object -ComObject WScript.Shell
$studioLinkPath = Join-Path $DesktopPath 'Metin2 Studio.lnk'
if (Test-Path -LiteralPath $studioLinkPath) {
    $existingStudioLink = $studioShell.CreateShortcut($studioLinkPath)
    if ($existingStudioLink.Arguments -ne $studioArguments) {
        $studioLinkPath = Join-Path $DesktopPath ('Metin2 Studio ' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.lnk')
    }
}
$studioShortcut = $studioShell.CreateShortcut($studioLinkPath)
$studioShortcut.TargetPath = $studioPowerShell
$studioShortcut.Arguments = $studioArguments
$studioShortcut.WorkingDirectory = $PSScriptRoot
$studioShortcut.Description = 'Start Metin2 Studio and open the dashboard. Does not restart the game.'
$studioShortcut.WindowStyle = 7
$studioIcon = Join-Path $PSScriptRoot 'data\studio.ico'
$studioShortcut.IconLocation = if (Test-Path -LiteralPath $studioIcon) { $studioIcon + ',0' } else { $studioPowerShell + ',0' }
$studioShortcut.Save()
$verifiedStudioLink = $studioShell.CreateShortcut($studioLinkPath)
if ($verifiedStudioLink.TargetPath -ne $studioPowerShell -or $verifiedStudioLink.Arguments -ne $studioArguments -or $verifiedStudioLink.WorkingDirectory -ne $PSScriptRoot) {
    throw 'Shortcut verification failed.'
}
Write-Output $studioLinkPath
