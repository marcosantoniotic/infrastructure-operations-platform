[CmdletBinding()]
param(
    [switch]$VerifyRestore,
    [switch]$VerifyIdempotence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$vagrantConfig = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$playbook = Join-Path $projectRoot 'playbooks\netbox-backup.yml'
$backupRole = Join-Path $projectRoot 'roles\netbox_backup'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $inventory,
    $groupVars,
    $vaultFile,
    $vaultPasswordFile,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}
if (-not (Test-Path -LiteralPath $backupRole -PathType Container)) {
    throw "Required role not found: $backupRole"
}

& $preflightRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before backup execution.'
}

$configuration = Get-Content -LiteralPath $vagrantConfig -Raw | ConvertFrom-Json
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$commonOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

Write-Host 'Staging the NetBox backup module on AUTOMATION-CONTROLLER.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare remote directories.' }

& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/netbox-backup.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the backup playbook.' }
& scp.exe @commonOptions $inventory "${controller}:$remoteRoot/inventories/validation/hosts.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the validation inventory.' }
& scp.exe @commonOptions $groupVars "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage validation variables.' }
& scp.exe @commonOptions $vaultFile "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
& scp.exe @commonOptions -r $backupRole "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the backup role.' }

$verifyValue = if ($VerifyRestore) { 'true' } else { 'false' }
Write-Host 'Creating a consistent backup and running the requested verification.'
& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/netbox-backup.yml -e netbox_backup_run_now=true -e netbox_backup_verify_restore=$verifyValue"
if ($LASTEXITCODE -ne 0) { throw 'NetBox backup validation failed.' }

if ($VerifyIdempotence) {
    Write-Host 'Executing the configuration-only idempotence pass.'
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/netbox-backup.yml -e netbox_backup_run_now=false -e netbox_backup_verify_restore=false"
    if ($LASTEXITCODE -ne 0) { throw 'NetBox backup idempotence validation failed.' }
}

Write-Host 'NetBox backup validation completed successfully.' -ForegroundColor Green
