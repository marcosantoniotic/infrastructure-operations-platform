[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'
$localConfig = Join-Path $projectRoot '.validation\vagrant.json'

if (-not (Get-Command vagrant -ErrorAction SilentlyContinue)) {
    throw 'Vagrant is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $localConfig -PathType Leaf)) {
    throw 'Local Vagrant configuration is missing. Run Initialize-Validation.ps1 first.'
}

$plugins = & vagrant plugin list
if ($plugins -notmatch 'vagrant-vmware-desktop') {
    throw 'The vagrant-vmware-desktop plugin is not installed.'
}

Push-Location $vagrantRoot
try {
    & vagrant up --provider=vmware_desktop
    if ($LASTEXITCODE -ne 0) {
        throw 'Vagrant environment startup failed.'
    }
    & vagrant status
}
finally {
    Pop-Location
}
