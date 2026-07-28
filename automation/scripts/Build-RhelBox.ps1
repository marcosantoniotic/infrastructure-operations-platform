[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$packerRoot = Join-Path $projectRoot 'automation\packer\rhel9'
$localVarsPath = Join-Path $packerRoot 'local.auto.pkrvars.hcl'
$boxPath = Join-Path $packerRoot 'output\rhel-9.8-vmware.box'

if (-not (Get-Command packer -ErrorAction SilentlyContinue)) {
    throw 'Packer is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $localVarsPath)) {
    throw 'Local Packer variables are missing. Run Initialize-Validation.ps1 first.'
}

Push-Location $packerRoot
try {
    & packer init .
    if ($LASTEXITCODE -ne 0) { throw 'packer init failed.' }

    & packer fmt -check .
    if ($LASTEXITCODE -ne 0) { throw 'packer fmt check failed.' }

    & packer validate .
    if ($LASTEXITCODE -ne 0) { throw 'packer validate failed.' }

    $buildArguments = @('build')
    if ($Force) {
        $buildArguments += '-force'
    }
    $buildArguments += '.'
    & packer @buildArguments
    if ($LASTEXITCODE -ne 0) { throw 'packer build failed.' }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $boxPath)) {
    throw "Expected Vagrant box was not generated: $boxPath"
}

Write-Host "RHEL VMware box generated: $boxPath"
