[CmdletBinding()]
param(
    [string[]]$Machine
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant\operational'
$localConfig = Join-Path $projectRoot '.operational\vagrant.json'

function Invoke-VagrantCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$ArgumentList,

        [Parameter(Mandatory)]
        [string]$FailureMessage,

        [switch]$CaptureOutput
    )

    # Windows PowerShell 5.1 can promote text written by a native command to
    # stderr to NativeCommandError when the caller uses Stop. Vagrant writes
    # informational warnings to stderr, so assess native-command success by its
    # process exit code while preserving the warning in the console output.
    $previousErrorActionPreference = $ErrorActionPreference
    $capturedOutput = [System.Collections.Generic.List[string]]::new()

    try {
        $ErrorActionPreference = 'Continue'

        & vagrant @ArgumentList 2>&1 | ForEach-Object {
            $line = $_.ToString()
            if ($CaptureOutput) {
                [void]$capturedOutput.Add($line)
            }
            else {
                Write-Host $line
            }
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "$FailureMessage (exit code $exitCode)."
    }

    if ($CaptureOutput) {
        return $capturedOutput.ToArray()
    }
}

if (-not (Get-Command vagrant -ErrorAction SilentlyContinue)) {
    throw 'Vagrant is not available in PATH.'
}
if (-not (Test-Path -LiteralPath $localConfig -PathType Leaf)) {
    throw 'Operational Vagrant configuration is missing. Run Initialize-Operational.ps1 first.'
}

$plugins = Invoke-VagrantCommand `
    -ArgumentList @('plugin', 'list') `
    -FailureMessage 'Unable to inspect the installed Vagrant plugins.' `
    -CaptureOutput
if (($plugins -join "`n") -notmatch 'vagrant-vmware-desktop') {
    throw 'The vagrant-vmware-desktop plugin is not installed.'
}

$arguments = @('up')
if ($Machine.Count -gt 0) {
    $arguments += $Machine
}
$arguments += '--provider=vmware_desktop'

Push-Location $vagrantRoot
try {
    Invoke-VagrantCommand `
        -ArgumentList $arguments `
        -FailureMessage 'Operational Vagrant environment startup failed.'

    Invoke-VagrantCommand `
        -ArgumentList @('status') `
        -FailureMessage 'Unable to inspect the operational Vagrant environment status.'
}
finally {
    Pop-Location
}
