[CmdletBinding()]
param(
    [switch]$Force,

    [string]$VarFile,

    [string]$BoxFileName = 'rhel-9.8-vmware.box'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$packerRoot = Join-Path $projectRoot 'automation\packer\rhel9'
$localVarsPath = if ([string]::IsNullOrWhiteSpace($VarFile)) {
    Join-Path $packerRoot 'local.auto.pkrvars.hcl'
}
else {
    [System.IO.Path]::GetFullPath($VarFile)
}
$boxPath = Join-Path $packerRoot "output\$BoxFileName"

if (-not (Get-Command packer -ErrorAction SilentlyContinue)) {
    throw 'Packer is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $localVarsPath)) {
    throw "Packer variables are missing: $localVarsPath"
}

Push-Location $packerRoot
try {
    & packer init .
    if ($LASTEXITCODE -ne 0) { throw 'packer init failed.' }

    & packer fmt -check .
    if ($LASTEXITCODE -ne 0) { throw 'packer fmt check failed.' }

    & packer validate -var-file $localVarsPath .
    if ($LASTEXITCODE -ne 0) { throw 'packer validate failed.' }

    $buildArguments = @('build', '-var-file', $localVarsPath)
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
