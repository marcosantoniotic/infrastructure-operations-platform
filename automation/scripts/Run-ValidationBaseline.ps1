[CmdletBinding()]
param(
    [switch]$VerifyIdempotence,

    [ValidateSet('platform', 'standby')]
    [string]$TargetGroup = 'platform',

    [string]$TargetHostname
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$vagrantConfig = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\bootstrap-rhel.yml'
$role = Join-Path $projectRoot 'roles\rhel_baseline'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $requirements,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}
if (-not (Test-Path -LiteralPath $role -PathType Container)) {
    throw "Required role not found: $role"
}

if ([string]::IsNullOrWhiteSpace($TargetHostname)) {
    $TargetHostname = if ($TargetGroup -eq 'standby') {
        'srv02-standby'
    }
    else {
        'srv01-validation'
    }
}

& $preflightRunner -TargetGroup $TargetGroup
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before baseline execution.'
}

$configuration = Get-Content -LiteralPath $vagrantConfig -Raw | ConvertFrom-Json
$controllerAddress = $configuration.controller_ip
$adminUsername = 'automation'
$controller = "$adminUsername@$controllerAddress"
$remoteRoot = "/home/$adminUsername/infrastructure-operations-platform"

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$groupVarsContent = @"
---
platform_hostname: $TargetHostname
platform_timezone: America/Sao_Paulo

rhel_apply_updates: true
rhel_reboot_after_updates: true
rhel_baseline_packages:
  - bash-completion
  - bind-utils
  - curl
  - git
  - jq
  - lsof
  - rsync
  - tar
  - unzip
  - vim-enhanced
  - wget

rhel_harden_ssh: false
rhel_ssh_allow_users: []
rhel_firewalld_enabled: true
rhel_selinux_state: enforcing
"@
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[System.IO.File]::WriteAllText($groupVars, $groupVarsContent, $utf8WithoutBom)

$commonOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

Write-Host 'Staging RHEL baseline automation on the controller.'
& ssh.exe @commonOptions $controller `
    "rm -f $remoteRoot/inventories/validation/group_vars/all.yml; install -d -m 0755 $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare baseline directories on the controller.'
}

& scp.exe @commonOptions $requirements "${controller}:$remoteRoot/requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage requirements.yml.' }
& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/bootstrap-rhel.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the baseline playbook.' }
& scp.exe @commonOptions $groupVars `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage baseline variables.' }
& scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the rhel_baseline role.' }

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install required Ansible collections.'
}

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing RHEL baseline: pass $run of $runs."
    $remoteBaseline = @"
set -e
cd $remoteRoot
if [ -f /home/$adminUsername/.ansible/vault-password ]; then
  ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/$adminUsername/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/bootstrap-rhel.yml -e target_group=$TargetGroup
else
  ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook -i inventories/validation/hosts.yml playbooks/bootstrap-rhel.yml -e target_group=$TargetGroup
fi
"@
    $remoteBaseline = $remoteBaseline -replace "`r`n", "`n"
    & ssh.exe @commonOptions $controller $remoteBaseline
    if ($LASTEXITCODE -ne 0) {
        throw "RHEL baseline failed on pass $run."
    }
}

Write-Host 'RHEL baseline execution completed successfully.' -ForegroundColor Green
