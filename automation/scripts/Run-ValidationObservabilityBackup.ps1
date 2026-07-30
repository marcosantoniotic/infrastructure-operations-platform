[CmdletBinding()]
param(
    [switch]$VerifyRestore,
    [switch]$VerifyPersistence,
    [switch]$VerifyIdempotence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configurationFile = Join-Path $validationRoot 'vagrant.json'
$inventory = Join-Path $validationRoot 'ansible\hosts.yml'
$groupVars = Join-Path $validationRoot 'ansible\group_vars\all\main.yml'
$vaultFile = Join-Path $validationRoot 'ansible\group_vars\all\vault.yml'
$playbook = Join-Path $projectRoot 'playbooks\observability-backup.yml'
$backupRole = Join-Path $projectRoot 'roles\observability_backup'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

foreach ($path in @(
    $privateKey,
    $configurationFile,
    $inventory,
    $groupVars,
    $vaultFile,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file was not found: $path"
    }
}
if (-not (Test-Path -LiteralPath $backupRole -PathType Container)) {
    throw "Required role was not found: $backupRole"
}

& $preflightRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before observability backup execution.'
}

$configuration = Get-Content -LiteralPath $configurationFile -Raw |
    ConvertFrom-Json
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$sshOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

$groupVarsContent = Get-Content -LiteralPath $groupVars -Raw
$sectionPattern = '(?ms)^# BEGIN VALIDATION OBSERVABILITY BACKUP\r?\n.*?^# END VALIDATION OBSERVABILITY BACKUP\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$backupSection = @'
# BEGIN VALIDATION OBSERVABILITY BACKUP
observability_backup_project_dir: /opt/observability
observability_backup_root: /var/backups/infrastructure-platform/observability
observability_backup_retention_days: 14
observability_backup_schedule: "*-*-* 03:45:00"
observability_backup_prometheus_image: prom/prometheus:v3.13.1
observability_backup_grafana_image: grafana/grafana:13.1.1
observability_backup_helper_image: alpine:3.23.3
observability_backup_run_now: false
observability_backup_verify_restore: false
observability_backup_metrics_dir: /var/lib/node_exporter/textfile_collector
# END VALIDATION OBSERVABILITY BACKUP
'@
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $backupSection + "`n",
    $utf8
)

Write-Host 'Staging the observability backup module on AUTOMATION-CONTROLLER.'
$remoteCommand = @"
set -eu
install -d -m 0755 \
  '$remoteRoot/playbooks' \
  '$remoteRoot/roles' \
  '$remoteRoot/inventories/validation/group_vars/all'
case '$remoteRoot/roles/observability_backup' in
  /home/automation/infrastructure-operations-platform/roles/observability_backup) ;;
  *) echo 'Unsafe observability backup role path.' >&2; exit 20 ;;
esac
sudo rm -rf '$remoteRoot/roles/observability_backup'
sudo chown -R automation:automation '$remoteRoot/roles'
"@ -replace "`r`n", "`n"
& ssh.exe @sshOptions $controller $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare the controller workspace.'
}

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/observability-backup.yml" },
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" },
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" },
    @{ Source = $vaultFile; Target = "$remoteRoot/inventories/validation/group_vars/all/vault.yml" }
)) {
    & scp.exe @sshOptions $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stage $($copy.Source)."
    }
}
& scp.exe @sshOptions -r $backupRole "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stage the observability backup role.'
}

$verifyValue = $VerifyRestore.IsPresent.ToString().ToLowerInvariant()
$remoteCommand = @"
set -eu
chmod 0600 '$remoteRoot/inventories/validation/group_vars/all/vault.yml'
cd '$remoteRoot'
ANSIBLE_ROLES_PATH='$remoteRoot/roles' ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/validation/hosts.yml \
  playbooks/observability-backup.yml \
  -e observability_backup_run_now=true \
  -e observability_backup_verify_restore=$verifyValue
"@ -replace "`r`n", "`n"
& ssh.exe @sshOptions $controller $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Observability backup validation failed.'
}

if ($VerifyPersistence) {
    Write-Host 'Reloading SRV01-VALIDATION to verify timer persistence.'
    Push-Location $vagrantRoot
    try {
        & vagrant.exe reload srv01-validation --no-provision
        if ($LASTEXITCODE -ne 0) {
            throw 'Vagrant reload failed during backup persistence validation.'
        }
    }
    finally {
        Pop-Location
    }

    $remoteCommand = @"
set -eu
ssh -o BatchMode=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  automation@$($configuration.platform_ip) \
  'sudo systemctl is-enabled observability-backup.timer &&
   sudo systemctl is-active observability-backup.timer &&
   sudo /usr/local/sbin/observability-backup verify'
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Observability backup persistence validation failed.'
    }
}

if ($VerifyIdempotence) {
    $remoteCommand = @"
set -eu
cd '$remoteRoot'
ANSIBLE_ROLES_PATH='$remoteRoot/roles' ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/validation/hosts.yml \
  playbooks/observability-backup.yml \
  -e observability_backup_run_now=false \
  -e observability_backup_verify_restore=false
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Observability backup idempotence validation failed.'
    }
}

Write-Host 'Observability backup and isolated restore validation completed successfully.' -ForegroundColor Green
