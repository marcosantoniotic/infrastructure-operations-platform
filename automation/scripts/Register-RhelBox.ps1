[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$boxPath = Join-Path $projectRoot 'automation\packer\rhel9\output\rhel-9.8-vmware.box'
$boxName = 'infrastructure-operations-platform/rhel9.8'

if (-not (Get-Command vagrant -ErrorAction SilentlyContinue)) {
    throw 'Vagrant is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $boxPath -PathType Leaf)) {
    throw "Vagrant box not found: $boxPath"
}

& vagrant box add --force --name $boxName $boxPath
if ($LASTEXITCODE -ne 0) {
    throw 'Vagrant box registration failed.'
}

Write-Host "Local Vagrant box registered: $boxName"
