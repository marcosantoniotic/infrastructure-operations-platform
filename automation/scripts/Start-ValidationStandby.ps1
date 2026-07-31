[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'
$localConfigPath = Join-Path $projectRoot '.validation\vagrant.json'

if (-not (Get-Command vagrant -ErrorAction SilentlyContinue)) {
    throw 'Vagrant is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $localConfigPath -PathType Leaf)) {
    throw 'Local Vagrant configuration is missing. Run Initialize-Validation.ps1 first.'
}

$localConfig = Get-Content -LiteralPath $localConfigPath -Raw |
    ConvertFrom-Json
if (-not $localConfig.standby_ip) {
    throw 'standby_ip is not configured. Rerun Initialize-Validation.ps1 with -StandbyAddress.'
}

$plugins = & vagrant plugin list
if ($plugins -notmatch 'vagrant-vmware-desktop') {
    throw 'The vagrant-vmware-desktop plugin is not installed.'
}

Push-Location $vagrantRoot
try {
    & vagrant up srv02-standby --provider=vmware_desktop --no-provision
    if ($LASTEXITCODE -ne 0) {
        throw 'Standby VM startup failed.'
    }
    & vagrant status srv02-standby
}
finally {
    Pop-Location
}
