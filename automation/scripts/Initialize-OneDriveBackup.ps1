[CmdletBinding()]
param(
    [string]$RemoteName = 'onedrive',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$toolsRoot = Join-Path $validationRoot 'tools'
$rcloneVersion = '1.74.4'
$archiveName = "rclone-v$rcloneVersion-windows-amd64.zip"
$archive = Join-Path $toolsRoot $archiveName
$expanded = Join-Path $toolsRoot "rclone-v$rcloneVersion-windows-amd64"
$rclone = Join-Path $expanded 'rclone.exe'
$config = Join-Path $validationRoot 'rclone-onedrive.conf'
$expectedHash = 'ef097ef9de37a57feb7d9f9c7afb34148ad3c65be8025f1d8f7f521554a701ea'

New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $rclone -PathType Leaf)) {
    Invoke-WebRequest `
        -Uri "https://downloads.rclone.org/v$rcloneVersion/$archiveName" `
        -OutFile $archive
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "rclone archive checksum mismatch. Expected $expectedHash; received $actualHash."
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolsRoot -Force
}

if ((Test-Path -LiteralPath $config) -and -not $Force) {
    Write-Host "Existing ignored OneDrive configuration found: $config"
    Write-Host 'Use -Force only when you intentionally need to reauthorize it.'
} else {
    Write-Host "Create a remote named '$RemoteName' and select Microsoft OneDrive."
    Write-Host 'The browser will be used once for Microsoft authorization.'
    & $rclone config --config $config
    if ($LASTEXITCODE -ne 0) {
        throw 'rclone OneDrive configuration did not complete successfully.'
    }
}

$remotes = & $rclone listremotes --config $config
if ($LASTEXITCODE -ne 0 -or "${RemoteName}:" -notin $remotes) {
    throw "Remote '${RemoteName}:' was not found in $config."
}

& $rclone lsd "${RemoteName}:" --config $config --max-depth 1
if ($LASTEXITCODE -ne 0) {
    throw 'The OneDrive remote exists but could not be accessed.'
}

Write-Host 'OneDrive authorization completed and connectivity validated.' -ForegroundColor Green
Write-Host "Sensitive ignored configuration: $config"
Write-Warning 'Do not copy this file into Git, screenshots, chat, or documentation.'
