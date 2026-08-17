[CmdletBinding()]
param(
    [switch]$VerifyIdempotence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configuration = Get-Content (Join-Path $validationRoot 'vagrant.json') -Raw |
    ConvertFrom-Json
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVars = Join-Path $ansibleRoot 'group_vars\all\main.yml'
$vaultFile = Join-Path $ansibleRoot 'group_vars\all\vault.yml'
$playbook = Join-Path $projectRoot 'playbooks\external-backup.yml'
$role = Join-Path $projectRoot 'roles\external_backup'
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$options = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL'
)
$utf8 = New-Object Text.UTF8Encoding($false)

$passwordFile = Join-Path $validationRoot 'external-backup-validation-password.txt'
if (Test-Path -LiteralPath $passwordFile -PathType Leaf) {
    $repositoryPassword = (Get-Content -LiteralPath $passwordFile -Raw).Trim()
} else {
    $passwordBytes = New-Object byte[] 32
    $randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomGenerator.GetBytes($passwordBytes)
    }
    finally {
        $randomGenerator.Dispose()
    }
    $repositoryPassword = [Convert]::ToBase64String($passwordBytes)
    [IO.File]::WriteAllText($passwordFile, $repositoryPassword, $utf8)
}
$content = Get-Content -LiteralPath $groupVars -Raw
$pattern = '(?ms)^# BEGIN VALIDATION EXTERNAL BACKUP\r?\n.*?^# END VALIDATION EXTERNAL BACKUP\r?\n?'
$content = [regex]::Replace($content, $pattern, '')
$section = @"
# BEGIN VALIDATION EXTERNAL BACKUP
external_backup_repository: /var/tmp/infrastructure-platform-restic-validation
external_backup_restic_password: "$repositoryPassword"
external_backup_rclone_config: "<NOT_REQUIRED_FOR_LOCAL_VALIDATION>"
external_backup_require_rclone: false
external_backup_schedule: "*-*-* 04:30:00"
external_backup_sources:
  - /var/backups/infrastructure-platform/netbox
  - /var/backups/infrastructure-platform/zabbix
  - /var/backups/infrastructure-platform/observability
  - /var/backups/infrastructure-platform/glpi
external_backup_keep_daily: 14
external_backup_keep_weekly: 8
external_backup_keep_monthly: 3
external_backup_metrics_dir: /var/lib/node_exporter/textfile_collector
external_backup_run_now: true
# END VALIDATION EXTERNAL BACKUP
"@
[IO.File]::WriteAllText($groupVars, $content.TrimEnd() + "`n`n" + $section, $utf8)

& ssh.exe @options $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; sudo rm -rf $remoteRoot/roles/external_backup; sudo chown -R automation:automation $remoteRoot"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare the controller.' }

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/external-backup.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
    @{ Source = $vaultFile; Target = "$remoteRoot/inventories/validation/group_vars/all/vault.yml" }
)) {
    & scp.exe @options $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $($copy.Source)." }
}
& scp.exe @options -r $role "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the external backup role.' }

& ssh.exe @options $controller `
    "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/external-backup.yml"
if ($LASTEXITCODE -ne 0) { throw 'External backup validation failed.' }

& ssh.exe @options $controller `
    "ssh -o BatchMode=yes -o StrictHostKeyChecking=no automation@$($configuration.platform_ip) 'sudo env RESTIC_REPOSITORY=/var/tmp/infrastructure-platform-restic-validation RESTIC_PASSWORD_FILE=/etc/infrastructure-backup/restic-password /usr/local/bin/restic snapshots --json | grep -q infrastructure-operations-platform && sudo grep infrastructure_external_backup_last_run_success /var/lib/node_exporter/textfile_collector/external_backup.prom | grep -q 1$'"
if ($LASTEXITCODE -ne 0) { throw 'External backup evidence validation failed.' }

if ($VerifyIdempotence) {
    & ssh.exe @options $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/external-backup.yml -e external_backup_run_now=false"
    if ($LASTEXITCODE -ne 0) { throw 'External backup idempotence validation failed.' }
}

Write-Host 'External backup validation completed successfully.' -ForegroundColor Green
