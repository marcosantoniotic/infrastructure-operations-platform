[CmdletBinding()]
param(
    [switch]$SkipRestore
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configurationFile = Join-Path $validationRoot 'vagrant.json'
$rcloneConfigFile = Join-Path $validationRoot 'rclone-onedrive.conf'
$resticPasswordFile = Join-Path $validationRoot 'onedrive-restic-password.txt'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVars = Join-Path $ansibleRoot 'group_vars\all\main.yml'
$encryptedVaultFile = Join-Path $ansibleRoot 'group_vars\all\external-backup-vault.yml'
$temporaryVaultFile = Join-Path $validationRoot 'external-backup-vault.tmp.yml'
$playbook = Join-Path $projectRoot 'playbooks\external-backup.yml'
$role = Join-Path $projectRoot 'roles\external_backup'
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$utf8 = New-Object Text.UTF8Encoding($false)

foreach ($requiredFile in @(
    $privateKey,
    $configurationFile,
    $rcloneConfigFile,
    $resticPasswordFile,
    $inventory,
    $groupVars,
    $playbook
)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required file was not found: $requiredFile"
    }
}

$configuration = Get-Content -LiteralPath $configurationFile -Raw |
    ConvertFrom-Json
$controller = "automation@$($configuration.controller_ip)"
$sshOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL'
)

function ConvertTo-YamlLiteral {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    return (($Value.TrimEnd() -split "\r?\n") |
        ForEach-Object { "  $_" }) -join "`n"
}

$repositoryPassword = (Get-Content -LiteralPath $resticPasswordFile -Raw).Trim()
$rcloneConfiguration = Get-Content -LiteralPath $rcloneConfigFile -Raw

if ($repositoryPassword.Length -lt 40) {
    throw 'The definitive Restic password is unexpectedly short.'
}
if ($rcloneConfiguration -notmatch '(?m)^\[onedrive\]\s*$') {
    throw "The rclone configuration does not contain the expected 'onedrive' remote."
}

$vaultPlaintext = @"
---
vault_external_backup_restic_password: |-
$(ConvertTo-YamlLiteral -Value $repositoryPassword)
vault_external_backup_rclone_config: |-
$(ConvertTo-YamlLiteral -Value $rcloneConfiguration)
"@

$groupVarsContent = Get-Content -LiteralPath $groupVars -Raw
$legacySectionPattern = '(?ms)^# BEGIN VALIDATION EXTERNAL BACKUP\r?\n.*?^# END VALIDATION EXTERNAL BACKUP\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $legacySectionPattern, '')
$sectionPattern = '(?ms)^# BEGIN VALIDATION ONEDRIVE BACKUP\r?\n.*?^# END VALIDATION ONEDRIVE BACKUP\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$groupVarsSection = @'
# BEGIN VALIDATION ONEDRIVE BACKUP
external_backup_repository: "rclone:onedrive:infrastructure-operations-platform/restic"
external_backup_restic_password: "{{ vault_external_backup_restic_password }}"
external_backup_rclone_config: "{{ vault_external_backup_rclone_config }}"
external_backup_require_rclone: true
external_backup_schedule: "*-*-* 04:30:00"
external_backup_randomized_delay: 15m
external_backup_sources:
  - /var/backups/infrastructure-platform/netbox
  - /var/backups/infrastructure-platform/zabbix
  - /var/backups/infrastructure-platform/observability
external_backup_keep_daily: 14
external_backup_keep_weekly: 8
external_backup_keep_monthly: 3
external_backup_metrics_dir: /var/lib/node_exporter/textfile_collector
external_backup_run_now: false
# END VALIDATION ONEDRIVE BACKUP
'@

try {
    [IO.File]::WriteAllText($temporaryVaultFile, $vaultPlaintext, $utf8)
    [IO.File]::WriteAllText(
        $groupVars,
        $groupVarsContent.TrimEnd() + "`n`n" + $groupVarsSection + "`n",
        $utf8
    )

    $remoteCommand = @"
set -eu
install -d -m 0755 \
  $remoteRoot/playbooks \
  $remoteRoot/roles \
  $remoteRoot/inventories/validation/group_vars/all
sudo rm -rf $remoteRoot/roles/external_backup
sudo chown -R automation:automation $remoteRoot
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to prepare the automation controller.'
    }

    & scp.exe @sshOptions $temporaryVaultFile "${controller}:/home/automation/external-backup-vault.tmp.yml"
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to transfer the temporary Vault source.'
    }

    $remoteCommand = @"
set -eu
chmod 0600 /home/automation/external-backup-vault.tmp.yml
ansible-vault encrypt \
  --vault-password-file /home/automation/.ansible/vault-password \
  --output $remoteRoot/inventories/validation/group_vars/all/external-backup-vault.yml \
  /home/automation/external-backup-vault.tmp.yml
rm -f /home/automation/external-backup-vault.tmp.yml
chmod 0600 $remoteRoot/inventories/validation/group_vars/all/external-backup-vault.yml
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the encrypted Ansible Vault file.'
    }

    foreach ($copy in @(
        @{ Source = $playbook; Target = "$remoteRoot/playbooks/external-backup.yml" }
        @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
        @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
    )) {
        & scp.exe @sshOptions $copy.Source "${controller}:$($copy.Target)"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to stage $($copy.Source)."
        }
    }

    & scp.exe @sshOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to stage the external backup role.'
    }

    $remoteCommand = @"
set -eu
cd $remoteRoot
ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/validation/hosts.yml \
  playbooks/external-backup.yml \
  -e external_backup_run_now=true
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'The OneDrive external backup deployment failed.'
    }

    $remoteCommand = @"
set -eu
ssh -o BatchMode=yes -o StrictHostKeyChecking=no automation@$($configuration.platform_ip) \
  'sudo env PATH=/usr/local/bin:/usr/bin:/bin RESTIC_REPOSITORY=rclone:onedrive:infrastructure-operations-platform/restic RESTIC_PASSWORD_FILE=/etc/infrastructure-backup/restic-password RCLONE_CONFIG=/etc/infrastructure-backup/rclone.conf /usr/local/bin/restic snapshots --compact && sudo grep -Eq infrastructure_external_backup_last_run_success.*[[:space:]]1$ /var/lib/node_exporter/textfile_collector/external_backup.prom && sudo systemctl is-enabled --quiet infrastructure-external-backup.timer && sudo systemctl is-active --quiet infrastructure-external-backup.timer'
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Snapshot, metric, or timer validation failed.'
    }

    if (-not $SkipRestore) {
        $remoteCommand = @"
set -eu
ssh -o BatchMode=yes -o StrictHostKeyChecking=no automation@$($configuration.platform_ip) \
  'sudo rm -rf /var/tmp/infrastructure-external-backup-restore-validation && sudo install -d -m 0700 /var/tmp/infrastructure-external-backup-restore-validation && sudo env PATH=/usr/local/bin:/usr/bin:/bin RESTIC_REPOSITORY=rclone:onedrive:infrastructure-operations-platform/restic RESTIC_PASSWORD_FILE=/etc/infrastructure-backup/restic-password RCLONE_CONFIG=/etc/infrastructure-backup/rclone.conf /usr/local/bin/restic restore latest --verify --target /var/tmp/infrastructure-external-backup-restore-validation && test "$(sudo find /var/tmp/infrastructure-external-backup-restore-validation/var/backups/infrastructure-platform -mindepth 3 -maxdepth 3 -name SHA256SUMS | wc -l)" -ge 3 && sudo env PATH=/usr/bin:/bin find /var/tmp/infrastructure-external-backup-restore-validation/var/backups/infrastructure-platform -mindepth 3 -maxdepth 3 -name SHA256SUMS -execdir sha256sum --check SHA256SUMS \; && sudo rm -rf /var/tmp/infrastructure-external-backup-restore-validation'
"@ -replace "`r`n", "`n"
        & ssh.exe @sshOptions $controller $remoteCommand
        if ($LASTEXITCODE -ne 0) {
            throw 'The encrypted OneDrive restore validation failed.'
        }
    }

    & scp.exe @sshOptions "${controller}:$remoteRoot/inventories/validation/group_vars/all/external-backup-vault.yml" $encryptedVaultFile
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to retain the encrypted validation Vault locally.'
    }
}
finally {
    $repositoryPassword = $null
    $rcloneConfiguration = $null
    $vaultPlaintext = $null
    Remove-Item -LiteralPath $temporaryVaultFile -Force -ErrorAction SilentlyContinue
    try {
        & ssh.exe @sshOptions $controller 'rm -f /home/automation/external-backup-vault.tmp.yml' 2>$null
    }
    catch {
        # Best-effort cleanup after the protected temporary file has been encrypted.
    }
}

Write-Host 'Encrypted OneDrive backup, metrics, timer and restore validation succeeded.' -ForegroundColor Green
