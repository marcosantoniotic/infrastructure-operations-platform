[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ControllerAddress,

    [Parameter(Mandatory)]
    [string]$PlatformAddress,

    [Parameter(Mandatory)]
    [string]$IsoPath,

    [string]$RecoveryAddress,

    [string]$StandbyAddress,

    [string]$IsoChecksum = 'c0dd53b73406b85b40d6168d1748e605d71361b2992d282c408b7d7d2e1d2c80',

    [string]$AdminUsername = 'automation',

    [string]$BoxName = 'infrastructure-operations-platform/rhel9.8-operational'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$operationalRoot = Join-Path $projectRoot '.operational'
$privateKeyPath = Join-Path $operationalRoot 'id_ed25519'
$publicKeyPath = "$privateKeyPath.pub"
$packerVarsPath = Join-Path $operationalRoot 'operational.pkrvars.hcl'
$vagrantConfigPath = Join-Path $operationalRoot 'vagrant.json'
$inventoryRoot = Join-Path $projectRoot 'inventories\operational'
$inventoryGroupVars = Join-Path $inventoryRoot 'group_vars'
$inventoryPath = Join-Path $inventoryRoot 'hosts.yml'
$exampleRoot = Join-Path $projectRoot 'inventories\examples\operational'
$baseAllVarsPath = Join-Path $projectRoot 'inventories\example\group_vars\all.yml'

function ConvertTo-HclString {
    param([Parameter(Mandatory)][string]$Value)
    return $Value.Replace('\', '/').Replace('"', '\"')
}

foreach ($address in @(
        $ControllerAddress,
        $PlatformAddress,
        $RecoveryAddress,
        $StandbyAddress
    )) {
    if ([string]::IsNullOrWhiteSpace($address)) {
        continue
    }
    $parsedAddress = $null
    if (-not [System.Net.IPAddress]::TryParse($address, [ref]$parsedAddress)) {
        throw "Invalid operational address: $address"
    }
}

if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) {
    throw "RHEL DVD ISO not found: $IsoPath"
}
if ($IsoChecksum -notmatch '^[a-fA-F0-9]{64}$') {
    throw 'IsoChecksum must be a SHA-256 value with 64 hexadecimal characters.'
}
if (-not (Get-Command ssh-keygen -ErrorAction SilentlyContinue)) {
    throw 'ssh-keygen is not available in PATH.'
}

New-Item -ItemType Directory -Path $operationalRoot -Force | Out-Null
New-Item -ItemType Directory -Path $inventoryGroupVars -Force | Out-Null

if (-not (Test-Path -LiteralPath $privateKeyPath)) {
    $keyArguments = (
        '-q -t ed25519 -a 100 -N "" ' +
        '-C "infrastructure-operations-platform-operational" ' +
        "-f `"$privateKeyPath`""
    )
    $keyProcess = Start-Process `
        -FilePath 'ssh-keygen.exe' `
        -ArgumentList $keyArguments `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($keyProcess.ExitCode -ne 0) {
        throw 'Operational SSH key generation failed.'
    }
}

if (-not (Test-Path -LiteralPath $publicKeyPath -PathType Leaf)) {
    throw "SSH public key not found: $publicKeyPath"
}

$randomBytes = New-Object byte[] 30
$randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomGenerator.GetBytes($randomBytes)
}
finally {
    $randomGenerator.Dispose()
}
$adminPassword = [Convert]::ToBase64String($randomBytes)
$publicKey = (Get-Content -LiteralPath $publicKeyPath -Raw).Trim()
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false

$packerVariables = @"
iso_path             = "$(ConvertTo-HclString $IsoPath)"
iso_checksum         = "$(ConvertTo-HclString $IsoChecksum.ToLowerInvariant())"
vm_name              = "RHEL9-IOP-OPS-BASE"
guest_hostname       = "rhel9-iop-ops-base"
admin_username       = "$(ConvertTo-HclString $AdminUsername)"
admin_password       = "$(ConvertTo-HclString $adminPassword)"
ssh_public_key       = "$(ConvertTo-HclString $publicKey)"
ssh_private_key_file = "$(ConvertTo-HclString $privateKeyPath)"
box_output_filename  = "rhel-9.8-operational-vmware.box"
disk_size_mb         = 81920
headless             = false
"@
[System.IO.File]::WriteAllText(
    $packerVarsPath,
    $packerVariables,
    $utf8WithoutBom
)

$vagrantConfiguration = [ordered]@{
    box_name        = $BoxName
    admin_username  = $AdminUsername
    ssh_private_key = $privateKeyPath
    controller_ip   = $ControllerAddress
    platform_ip     = $PlatformAddress
    resources       = [ordered]@{
        controller = [ordered]@{ cpus = 2; memory_mb = 4096 }
        platform   = [ordered]@{ cpus = 4; memory_mb = 8192 }
        recovery   = [ordered]@{ cpus = 4; memory_mb = 8192 }
        standby    = [ordered]@{ cpus = 2; memory_mb = 4096 }
    }
}
if (-not [string]::IsNullOrWhiteSpace($RecoveryAddress)) {
    $vagrantConfiguration.recovery_ip = $RecoveryAddress
}
if (-not [string]::IsNullOrWhiteSpace($StandbyAddress)) {
    $vagrantConfiguration.standby_ip = $StandbyAddress
}
[System.IO.File]::WriteAllText(
    $vagrantConfigPath,
    ($vagrantConfiguration | ConvertTo-Json -Depth 5),
    $utf8WithoutBom
)

$ansibleInventory = @"
---
all:
  children:
    automation_controller:
      hosts:
        iop-ops-automation-01:
          ansible_host: "$ControllerAddress"
          ansible_user: "$AdminUsername"
          ansible_become: true
    platform:
      hosts:
        iop-ops-platform-01:
          ansible_host: "$PlatformAddress"
          ansible_user: "$AdminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$AdminUsername/.ssh/id_ed25519"
"@
if (-not [string]::IsNullOrWhiteSpace($RecoveryAddress)) {
    $ansibleInventory += "`n" + @"
    recovery:
      hosts:
        iop-ops-recovery-01:
          ansible_host: "$RecoveryAddress"
          ansible_user: "$AdminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$AdminUsername/.ssh/id_ed25519"
"@
}
if (-not [string]::IsNullOrWhiteSpace($StandbyAddress)) {
    $ansibleInventory += "`n" + @"
    standby:
      hosts:
        iop-ops-standby-01:
          ansible_host: "$StandbyAddress"
          ansible_user: "$AdminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$AdminUsername/.ssh/id_ed25519"
"@
}
[System.IO.File]::WriteAllText(
    $inventoryPath,
    $ansibleInventory,
    $utf8WithoutBom
)

$allVarsDestination = Join-Path $inventoryGroupVars 'all.yml'
if (-not (Test-Path -LiteralPath $allVarsDestination)) {
    $allVars = Get-Content -LiteralPath $baseAllVarsPath -Raw
    $allVars = $allVars.Replace(
        'platform_hostname: srv01-validation',
        'platform_hostname: iop-ops-platform-01'
    )
    [System.IO.File]::WriteAllText(
        $allVarsDestination,
        $allVars,
        $utf8WithoutBom
    )
}
$vaultDestination = Join-Path $inventoryGroupVars 'vault.yml'
if (-not (Test-Path -LiteralPath $vaultDestination)) {
    Copy-Item `
        -LiteralPath (Join-Path $exampleRoot 'group_vars\vault.example.yml') `
        -Destination $vaultDestination
}

Write-Host 'Operational local configuration created.'
Write-Host "SSH private key: $privateKeyPath"
Write-Host "Packer variables: $packerVarsPath"
Write-Host "Vagrant configuration: $vagrantConfigPath"
Write-Host "Private Ansible inventory: $inventoryPath"
Write-Warning 'The generated files are ignored by Git.'
Write-Warning 'Replace private inventory placeholders and encrypt vault.yml before deployment.'
