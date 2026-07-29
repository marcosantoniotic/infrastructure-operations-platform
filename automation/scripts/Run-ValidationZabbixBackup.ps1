[CmdletBinding()]
param(
    [switch]$VerifyRestore,
    [switch]$VerifyIdempotence,
    [switch]$VerifyPersistence
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
$playbook = Join-Path $projectRoot 'playbooks\zabbix-backup.yml'
$backupRole = Join-Path $projectRoot 'roles\zabbix_backup'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $inventory,
    $groupVars,
    $vaultFile,
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
    throw 'Validation preflight failed before Zabbix backup execution.'
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

$groupVarsContent = Get-Content -LiteralPath $groupVars -Raw
$sectionPattern = '(?ms)^# BEGIN VALIDATION ZABBIX BACKUP\r?\n.*?^# END VALIDATION ZABBIX BACKUP\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$section = @'
# BEGIN VALIDATION ZABBIX BACKUP
zabbix_backup_project_dir: /opt/zabbix
zabbix_backup_root: /var/backups/infrastructure-platform/zabbix
zabbix_backup_retention_days: 14
zabbix_backup_schedule: "*-*-* 03:15:00"
zabbix_backup_mysql_service: mysql
zabbix_backup_server_service: zabbix-server
zabbix_backup_database_name: zabbix
zabbix_backup_mysql_image: mysql:8.4.10-oraclelinux9
zabbix_backup_run_now: false
zabbix_backup_verify_restore: false
# END VALIDATION ZABBIX BACKUP
'@
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $section.Trim() + "`n",
    $utf8WithoutBom
)

Write-Host 'Staging the Zabbix backup module on AUTOMATION-CONTROLLER.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare remote directories.' }

& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/zabbix-backup.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Zabbix backup playbook.' }
& scp.exe @commonOptions $inventory "${controller}:$remoteRoot/inventories/validation/hosts.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the validation inventory.' }
& scp.exe @commonOptions $groupVars "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage validation variables.' }
& scp.exe @commonOptions $vaultFile "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
& scp.exe @commonOptions -r $backupRole "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Zabbix backup role.' }

$verifyValue = if ($VerifyRestore) { 'true' } else { 'false' }
Write-Host 'Creating a consistent Zabbix backup and running the requested verification.'
& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/zabbix-backup.yml -e zabbix_backup_run_now=true -e zabbix_backup_verify_restore=$verifyValue"
if ($LASTEXITCODE -ne 0) { throw 'Zabbix backup validation failed.' }

if ($VerifyPersistence) {
    Write-Host 'Reloading SRV01-VALIDATION to verify the Zabbix backup schedule persistence.'
    Push-Location $vagrantRoot
    try {
        & vagrant.exe reload srv01-validation --no-provision
        if ($LASTEXITCODE -ne 0) {
            throw 'Vagrant reload failed during Zabbix backup persistence validation.'
        }
    }
    finally {
        Pop-Location
    }

    Write-Host 'Checking timer and backup artifacts after reload.'
    & ssh.exe @commonOptions $controller `
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null automation@$($configuration.platform_ip) 'sudo systemctl is-enabled zabbix-backup.timer; sudo systemctl is-active zabbix-backup.timer; sudo /usr/local/sbin/zabbix-backup verify'"
    if ($LASTEXITCODE -ne 0) { throw 'Zabbix backup persistence validation failed.' }
}

if ($VerifyIdempotence) {
    Write-Host 'Executing the configuration-only idempotence pass.'
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/zabbix-backup.yml -e zabbix_backup_run_now=false -e zabbix_backup_verify_restore=false"
    if ($LASTEXITCODE -ne 0) { throw 'Zabbix backup idempotence validation failed.' }
}

Write-Host 'Zabbix backup validation completed successfully.' -ForegroundColor Green
