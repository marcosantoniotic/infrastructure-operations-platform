[CmdletBinding()]
param(
    [string[]]$Machine
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant\operational'
$localConfig = Join-Path $projectRoot '.operational\vagrant.json'

if (-not (Get-Command vagrant -ErrorAction SilentlyContinue)) {
    throw 'Vagrant is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $localConfig -PathType Leaf)) {
    throw 'Operational Vagrant configuration is missing. Run Initialize-Operational.ps1 first.'
}

$plugins = & vagrant plugin list
if ($plugins -notmatch 'vagrant-vmware-desktop') {
    throw 'The vagrant-vmware-desktop plugin is not installed.'
}

$arguments = @('up')
if ($Machine.Count -gt 0) {
    $arguments += $Machine
}
$arguments += '--provider=vmware_desktop'

Push-Location $vagrantRoot
try {
    & vagrant @arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Operational Vagrant environment startup failed.'
    }
    & vagrant status
}
finally {
    Pop-Location
}
