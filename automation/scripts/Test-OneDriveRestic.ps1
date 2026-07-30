[CmdletBinding()]
param(
    [switch]$KeepRepository
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$toolsRoot = Join-Path $validationRoot 'tools'
$rcloneRoot = Join-Path $toolsRoot 'rclone-v1.74.4-windows-amd64'
$rclone = Join-Path $rcloneRoot 'rclone.exe'
$rcloneConfig = Join-Path $validationRoot 'rclone-onedrive.conf'
$resticRoot = Join-Path $toolsRoot 'restic-v0.19.1-windows-amd64'
$restic = Join-Path $resticRoot 'restic.exe'
$archive = Join-Path $toolsRoot 'restic_0.19.1_windows_amd64.zip'
$expectedHash = 'da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d'
$remotePath = 'infrastructure-operations-platform/validation-smoke-test'
$repository = "rclone:onedrive:$remotePath"
$testRoot = Join-Path $validationRoot 'onedrive-restic-smoke'
$source = Join-Path $testRoot 'source'
$restore = Join-Path $testRoot 'restore'

foreach ($required in @($rclone, $rcloneConfig)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required OneDrive validation artifact not found: $required"
    }
}

New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $restic -PathType Leaf)) {
    Invoke-WebRequest `
        -Uri 'https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_windows_amd64.zip' `
        -OutFile $archive
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "Restic archive checksum mismatch. Expected $expectedHash; received $actualHash."
    }
    New-Item -ItemType Directory -Path $resticRoot -Force | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $resticRoot -Force
    $expandedBinary = Get-ChildItem -Path $resticRoot -Filter 'restic*.exe' |
        Select-Object -First 1
    if ($null -eq $expandedBinary) {
        throw 'Restic binary was not found after extraction.'
    }
    if ($expandedBinary.FullName -ne $restic) {
        Move-Item -LiteralPath $expandedBinary.FullName -Destination $restic
    }
}

if (Test-Path -LiteralPath $testRoot) {
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $source, $restore -Force | Out-Null
$payload = Join-Path $source 'validation.txt'
$random = New-Object byte[] 64
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($random)
} finally {
    $generator.Dispose()
}
[IO.File]::WriteAllText(
    $payload,
    "Infrastructure Operations Platform OneDrive validation`r`n$([Convert]::ToBase64String($random))",
    (New-Object Text.UTF8Encoding($false))
)
$sourceHash = (Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash

$passwordBytes = New-Object byte[] 32
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($passwordBytes)
} finally {
    $generator.Dispose()
}

$previousPath = $env:PATH
$previousRepository = $env:RESTIC_REPOSITORY
$previousPassword = $env:RESTIC_PASSWORD
$previousRcloneConfig = $env:RCLONE_CONFIG
$env:PATH = "$rcloneRoot;$previousPath"
$env:RESTIC_REPOSITORY = $repository
$env:RESTIC_PASSWORD = [Convert]::ToBase64String($passwordBytes)
$env:RCLONE_CONFIG = $rcloneConfig

try {
    & $restic init
    if ($LASTEXITCODE -ne 0) { throw 'Unable to initialize encrypted OneDrive repository.' }
    & $restic backup $source --tag onedrive-smoke-test
    if ($LASTEXITCODE -ne 0) { throw 'Unable to write encrypted OneDrive snapshot.' }
    & $restic check --read-data
    if ($LASTEXITCODE -ne 0) { throw 'Encrypted OneDrive repository verification failed.' }
    & $restic restore latest --target $restore
    if ($LASTEXITCODE -ne 0) { throw 'Unable to restore encrypted OneDrive snapshot.' }
    $restoredFile = Get-ChildItem -Path $restore -Recurse -Filter validation.txt |
        Select-Object -First 1
    if ($null -eq $restoredFile) { throw 'Restored validation file was not found.' }
    $restoredHash = (Get-FileHash -LiteralPath $restoredFile.FullName -Algorithm SHA256).Hash
    if ($restoredHash -ne $sourceHash) { throw 'Restored validation checksum does not match.' }
} finally {
    $env:PATH = $previousPath
    $env:RESTIC_REPOSITORY = $previousRepository
    $env:RESTIC_PASSWORD = $previousPassword
    $env:RCLONE_CONFIG = $previousRcloneConfig
}

if (-not $KeepRepository) {
    & $rclone purge "onedrive:$remotePath" --config $rcloneConfig
    if ($LASTEXITCODE -ne 0) {
        throw "Validation succeeded, but the test path could not be removed: $remotePath"
    }
}
Remove-Item -LiteralPath $testRoot -Recurse -Force

Write-Host 'Encrypted OneDrive write, check and restore validation succeeded.' -ForegroundColor Green
