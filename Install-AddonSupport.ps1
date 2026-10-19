$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Studio-Tools.ps1')
$addonPython = Get-StudioPython
& $addonPython -c 'import sys,struct; assert sys.version_info >= (3,11) and struct.calcsize("P")==8, "Client pack support requires 64-bit Python 3.11 or newer."'
if ($LASTEXITCODE -ne 0) { throw 'Choose 64-bit Python 3.11 or newer for optional add-on pack support.' }
& $addonPython -m pip install --only-binary=:all: --upgrade --requirement (Join-Path $PSScriptRoot 'requirements-addons.txt') --target (Join-Path $PSScriptRoot '.vendor')
if ($LASTEXITCODE -ne 0) { throw 'Optional dependencies could not be installed. Server editing remains available.' }
Write-Host 'Client pack support installed in this Studio folder. Restart Studio to use it.'
