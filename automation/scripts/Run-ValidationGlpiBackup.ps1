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
$playbook = Join-Path $projectRoot 'playbooks\glpi-backup.yml'
$backupRole = Join-Path $projectRoot 'roles\glpi_backup'
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
    throw 'Validation preflight failed before GLPI backup execution.'
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
$sectionPattern = '(?ms)^# BEGIN VALIDATION GLPI BACKUP\r?\n.*?^# END VALIDATION GLPI BACKUP\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$section = @'
# BEGIN VALIDATION GLPI BACKUP
glpi_backup_project_dir: /opt/glpi
glpi_backup_root: /var/backups/infrastructure-platform/glpi
glpi_backup_retention_days: 14
glpi_backup_schedule: "*-*-* 03:30:00"
glpi_backup_database_service: db
glpi_backup_application_service: glpi
glpi_backup_database_name: glpi
glpi_backup_database_image: mariadb:11.8.8
glpi_backup_helper_image: alpine:3.23.3
glpi_backup_run_now: false
glpi_backup_verify_restore: false
# END VALIDATION GLPI BACKUP
'@
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $section.Trim() + "`n",
    $utf8WithoutBom
)

Write-Host 'Staging the GLPI backup module on AUTOMATION-CONTROLLER.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; sudo rm -rf $remoteRoot/roles/glpi_backup; sudo chown -R automation:automation $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare remote directories.' }

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/glpi-backup.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
    @{ Source = $vaultFile; Target = "$remoteRoot/inventories/validation/group_vars/all/vault.yml" }
)) {
    & scp.exe @commonOptions $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $($copy.Source)." }
}
& scp.exe @commonOptions -r $backupRole "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the GLPI backup role.' }

$verifyValue = if ($VerifyRestore) { 'true' } else { 'false' }
Write-Host 'Creating a consistent GLPI backup and running the requested verification.'
& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/glpi-backup.yml -e glpi_backup_run_now=true -e glpi_backup_verify_restore=$verifyValue"
if ($LASTEXITCODE -ne 0) { throw 'GLPI backup validation failed.' }

if ($VerifyPersistence) {
    Write-Host 'Reloading SRV01-VALIDATION to verify the GLPI backup schedule persistence.'
    Push-Location $vagrantRoot
    try {
        & vagrant.exe reload srv01-validation --no-provision
        if ($LASTEXITCODE -ne 0) {
            throw 'Vagrant reload failed during GLPI backup persistence validation.'
        }
    }
    finally {
        Pop-Location
    }

    Write-Host 'Checking timer, metrics and restored artifacts after reload.'
    & ssh.exe @commonOptions $controller `
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null automation@$($configuration.platform_ip) 'sudo systemctl is-enabled glpi-backup.timer; sudo systemctl is-active glpi-backup.timer; sudo grep infrastructure_backup_last_run_success /var/lib/node_exporter/textfile_collector/glpi_backup.prom | grep -q 1$; sudo /usr/local/sbin/glpi-backup verify'"
    if ($LASTEXITCODE -ne 0) { throw 'GLPI backup persistence validation failed.' }
}

if ($VerifyIdempotence) {
    Write-Host 'Executing the configuration-only idempotence pass.'
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/glpi-backup.yml -e glpi_backup_run_now=false -e glpi_backup_verify_restore=false"
    if ($LASTEXITCODE -ne 0) { throw 'GLPI backup idempotence validation failed.' }
}

Write-Host 'GLPI backup validation completed successfully.' -ForegroundColor Green
