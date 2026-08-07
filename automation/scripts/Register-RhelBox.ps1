[CmdletBinding()]
param(
    [string]$BoxPath,

    [string]$BoxName = 'infrastructure-operations-platform/rhel9.8'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$resolvedBoxPath = if ([string]::IsNullOrWhiteSpace($BoxPath)) {
    Join-Path $projectRoot 'automation\packer\rhel9\output\rhel-9.8-vmware.box'
}
else {
    [System.IO.Path]::GetFullPath($BoxPath)
}

if (-not (Get-Command vagrant -ErrorAction SilentlyContinue)) {
    throw 'Vagrant is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $resolvedBoxPath -PathType Leaf)) {
    throw "Vagrant box not found: $resolvedBoxPath"
}

& vagrant box add --force --name $BoxName $resolvedBoxPath
if ($LASTEXITCODE -ne 0) {
    throw 'Vagrant box registration failed.'
}

Write-Host "Local Vagrant box registered: $BoxName"
