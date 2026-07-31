[CmdletBinding()]
param(
    [ValidateSet('platform', 'standby')]
    [string]$TargetGroup = 'platform'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$vagrantConfig = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$playbook = Join-Path $projectRoot 'playbooks\preflight.yml'

foreach ($path in @($privateKey, $vagrantConfig, $playbook)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}

$configuration = Get-Content -LiteralPath $vagrantConfig -Raw | ConvertFrom-Json
$controllerAddress = $configuration.controller_ip
$platformAddress = $configuration.platform_ip
$standbyAddress = $configuration.standby_ip
$adminUsername = 'automation'

if ($TargetGroup -eq 'standby' -and -not $standbyAddress) {
    throw 'standby_ip is not configured in .validation/vagrant.json.'
}
$targetAddress = if ($TargetGroup -eq 'standby') {
    $standbyAddress
}
else {
    $platformAddress
}
$targetHostname = if ($TargetGroup -eq 'standby') {
    'srv02-standby'
}
else {
    'srv01-validation'
}
$minimumMemoryMb = if ($TargetGroup -eq 'standby') { 3500 } else { 4096 }

New-Item -ItemType Directory -Path $ansibleRoot -Force | Out-Null
$inventoryContent = @"
---
all:
  children:
    platform:
      hosts:
        srv01-validation:
          ansible_host: "$platformAddress"
          ansible_user: "$adminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$adminUsername/.ssh/id_ed25519"
"@
if ($standbyAddress) {
    $inventoryContent += "`n" + @"
    standby:
      hosts:
        srv02-standby:
          ansible_host: "$standbyAddress"
          ansible_user: "$adminUsername"
          ansible_become: true
          ansible_ssh_private_key_file: "/home/$adminUsername/.ssh/id_ed25519"
"@
}
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
$inventoryContent = $inventoryContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($inventory, $inventoryContent, $utf8WithoutBom)

$sshOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)
$scpOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)
$controller = "$adminUsername@$controllerAddress"
$remoteRoot = "/home/$adminUsername/infrastructure-operations-platform"

Write-Host "Preparing Ansible controller: $controllerAddress"
& ssh.exe @sshOptions $controller `
    "install -d -m 0700 /home/$adminUsername/.ssh; install -d -m 0755 $remoteRoot/playbooks $remoteRoot/inventories/validation"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare the automation controller.'
}

& scp.exe @scpOptions $privateKey "${controller}:/tmp/validation_id_ed25519"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stage the validation SSH key.'
}
& scp.exe @scpOptions $inventory "${controller}:$remoteRoot/inventories/validation/hosts.yml"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stage the validation inventory.'
}
& scp.exe @scpOptions $playbook "${controller}:$remoteRoot/playbooks/preflight.yml"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stage the preflight playbook.'
}

$remotePreflight = @"
set -e
install -m 0600 /tmp/validation_id_ed25519 /home/$adminUsername/.ssh/id_ed25519
rm -f /tmp/validation_id_ed25519
touch /home/$adminUsername/.ssh/known_hosts
ssh-keygen -F $targetAddress -f /home/$adminUsername/.ssh/known_hosts >/dev/null ||
  ssh-keyscan -H $targetAddress >> /home/$adminUsername/.ssh/known_hosts
cd $remoteRoot
ansible $TargetGroup -i inventories/validation/hosts.yml --list-hosts |
  grep -q -- '$targetHostname'
if [ -f /home/$adminUsername/.ansible/vault-password ]; then
  ansible-playbook --vault-password-file /home/$adminUsername/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/preflight.yml -e target_group=$TargetGroup -e minimum_memory_mb=$minimumMemoryMb
else
  ansible-playbook -i inventories/validation/hosts.yml playbooks/preflight.yml -e target_group=$TargetGroup -e minimum_memory_mb=$minimumMemoryMb
fi
"@
$remotePreflight = $remotePreflight -replace "`r`n", "`n"
& ssh.exe @sshOptions $controller $remotePreflight
if ($LASTEXITCODE -ne 0) {
    throw 'Ansible preflight failed.'
}

Write-Host 'Ansible preflight completed successfully.' -ForegroundColor Green
