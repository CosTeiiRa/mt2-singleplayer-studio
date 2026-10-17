param(
    [Parameter(Mandatory=$true)][string]$ServerRoot,
    [Parameter(Mandatory=$true)][string]$PackagePath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedHash,
    [Parameter(Mandatory=$true)][string]$PackageVersion,
    [Parameter(Mandatory=$true)][ValidateSet('protected','ordinary')][string]$PackageKind,
    [Parameter(Mandatory=$true)][string]$ResultPath
)
$ErrorActionPreference = 'Stop'
$env:M2_LAUNCHER_LANGUAGE = 'en'
$studioServer = (Resolve-Path -LiteralPath $ServerRoot).Path
$studioPackage = (Resolve-Path -LiteralPath $PackagePath).Path
$studioModule = Join-Path $studioServer 'launcher\Metin2Launcher.psm1'
if (-not (Test-Path -LiteralPath $studioModule -PathType Leaf)) { throw 'The native launcher module is unavailable.' }
if ((Get-FileHash -LiteralPath $studioPackage -Algorithm SHA256).Hash -ine $ExpectedHash) { throw 'The reviewed package hash changed.' }
Import-Module -Name $studioModule -Force
$studioComponent = [pscustomobject]@{ url=$studioPackage; sha256=$ExpectedHash; version=$PackageVersion }
# The native function retains the package, protected-installation, path,
# backup and rollback checks. It does not build or restart the game.
$studioResult = Invoke-M2PackageUpdate -Component $studioComponent -TargetRoot $studioServer -BackupRoot (Join-Path $studioServer 'backups') -ServerPackage $PackageKind
$studioResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
# Match the native launcher's pending-build protocol. It must not mistake new
# files on disk for an already built and running game.
Set-Content -LiteralPath (Join-Path $studioServer '.m2launcher-rebuild-pending') -Value ([DateTime]::UtcNow.ToString('o')) -Encoding UTF8
$studioStatePath = Join-Path $studioServer '.m2launcher-state.json'
$studioState = [ordered]@{ schema=1; server=$PackageVersion; client='' }
if (Test-Path -LiteralPath $studioStatePath) {
    try {
        $studioPrevious = Get-Content -LiteralPath $studioStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($studioPrevious.PSObject.Properties['client']) { $studioState.client = [string]$studioPrevious.client }
    } catch { }
}
$studioState | ConvertTo-Json | Set-Content -LiteralPath $studioStatePath -Encoding UTF8
