[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ControllerAddress,

    [Parameter(Mandatory)]
    [string]$PlatformAddress,

    [string]$RecoveryAddress,

    [string]$StandbyAddress,

    [string]$IsoPath = 'D:\ISOs\rhel-9.8-x86_64-dvd.iso',
    [string]$AdminUsername = 'automation'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$packerRoot = Join-Path $projectRoot 'automation\packer\rhel9'
$privateKeyPath = Join-Path $validationRoot 'id_ed25519'
$publicKeyPath = "$privateKeyPath.pub"
$localVarsPath = Join-Path $packerRoot 'local.auto.pkrvars.hcl'
$vagrantConfigPath = Join-Path $validationRoot 'vagrant.json'
$ansibleValidationRoot = Join-Path $validationRoot 'ansible'
$ansibleInventoryPath = Join-Path $ansibleValidationRoot 'hosts.yml'

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
        throw "Invalid validation address: $address"
    }
}

if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) {
    throw "RHEL DVD ISO not found: $IsoPath"
}

if (-not (Get-Command ssh-keygen -ErrorAction SilentlyContinue)) {
    throw 'ssh-keygen is not available in PATH.'
}

New-Item -ItemType Directory -Path $validationRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ansibleValidationRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $privateKeyPath)) {
    $keyArguments = (
        '-q -t ed25519 -a 100 -N "" ' +
        '-C "infrastructure-operations-platform-validation" ' +
        "-f `"$privateKeyPath`""
    )
    $keyProcess = Start-Process `
        -FilePath 'ssh-keygen.exe' `
        -ArgumentList $keyArguments `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($keyProcess.ExitCode -ne 0) {
        throw 'SSH key generation failed.'
    }
}

if (-not (Test-Path -LiteralPath $publicKeyPath)) {
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

$packerVariables = @"
iso_path             = "$(ConvertTo-HclString $IsoPath)"
iso_checksum         = "c0dd53b73406b85b40d6168d1748e605d71361b2992d282c408b7d7d2e1d2c80"
admin_username       = "$(ConvertTo-HclString $AdminUsername)"
admin_password       = "$(ConvertTo-HclString $adminPassword)"
ssh_public_key       = "$(ConvertTo-HclString $publicKey)"
ssh_private_key_file = "$(ConvertTo-HclString $privateKeyPath)"
headless             = false
"@

$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[System.IO.File]::WriteAllText($localVarsPath, $packerVariables, $utf8WithoutBom)

$vagrantConfiguration = [ordered]@{
    controller_ip = $ControllerAddress
    platform_ip   = $PlatformAddress
}
if (-not [string]::IsNullOrWhiteSpace($RecoveryAddress)) {
    $vagrantConfiguration.recovery_ip = $RecoveryAddress
}
if (-not [string]::IsNullOrWhiteSpace($StandbyAddress)) {
    $vagrantConfiguration.standby_ip = $StandbyAddress
}
$vagrantJson = $vagrantConfiguration | ConvertTo-Json
[System.IO.File]::WriteAllText($vagrantConfigPath, $vagrantJson, $utf8WithoutBom)

$ansibleInventory = @"
---
all:
  children:
    platform:
      hosts:
        srv01-validation:
          ansible_host: "$PlatformAddress"
          ansible_user: "$AdminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$AdminUsername/.ssh/id_ed25519"
"@
if (-not [string]::IsNullOrWhiteSpace($StandbyAddress)) {
    $ansibleInventory += "`n" + @"
    standby:
      hosts:
        srv02-standby:
          ansible_host: "$StandbyAddress"
          ansible_user: "$AdminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$AdminUsername/.ssh/id_ed25519"
"@
}
[System.IO.File]::WriteAllText(
    $ansibleInventoryPath,
    $ansibleInventory,
    $utf8WithoutBom
)

Write-Host 'Local validation configuration created.'
Write-Host "SSH private key: $privateKeyPath"
Write-Host "Packer variables: $localVarsPath"
Write-Host "Vagrant addresses: $vagrantConfigPath"
Write-Host "Ansible inventory: $ansibleInventoryPath"
Write-Warning 'The generated files are ignored by Git. Do not copy their contents into commits or screenshots.'
