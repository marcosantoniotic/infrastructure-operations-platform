[CmdletBinding()]
param(
    [switch]$ApplyUpdates,
    [switch]$RefreshContainerImages,
    [switch]$RunExternalBackup
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configurationFile = Join-Path $validationRoot 'vagrant.json'
$inventory = Join-Path $validationRoot 'ansible\hosts.yml'
$groupVars = Join-Path $validationRoot 'ansible\group_vars\all\main.yml'
$vaultFile = Join-Path $validationRoot 'ansible\group_vars\all\vault.yml'
$playbook = Join-Path $projectRoot 'playbooks\maintenance-window.yml'
$role = Join-Path $projectRoot 'roles\maintenance_window'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

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
if (-not (Test-Path -LiteralPath $role -PathType Container)) {
    throw "Required role was not found: $role"
}

& $preflightRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before maintenance execution.'
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

$remoteCommand = @"
set -eu
install -d -m 0755 \
  '$remoteRoot/playbooks' \
  '$remoteRoot/roles' \
  '$remoteRoot/inventories/validation/group_vars/all'
case '$remoteRoot/roles/maintenance_window' in
  /home/automation/infrastructure-operations-platform/roles/maintenance_window) ;;
  *) echo 'Unsafe maintenance role path.' >&2; exit 20 ;;
esac
sudo rm -rf '$remoteRoot/roles/maintenance_window'
sudo chown -R automation:automation '$remoteRoot/roles'
"@ -replace "`r`n", "`n"
& ssh.exe @sshOptions $controller $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare the controller workspace.'
}

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/maintenance-window.yml" },
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" },
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" },
    @{ Source = $vaultFile; Target = "$remoteRoot/inventories/validation/group_vars/all/vault.yml" }
)) {
    & scp.exe @sshOptions $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stage $($copy.Source)."
    }
}
& scp.exe @sshOptions -r $role "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stage the maintenance role.'
}

$applyUpdatesValue = $ApplyUpdates.IsPresent.ToString().ToLowerInvariant()
$refreshImagesValue = $RefreshContainerImages.IsPresent.ToString().ToLowerInvariant()
$externalBackupValue = $RunExternalBackup.IsPresent.ToString().ToLowerInvariant()
$changeReference = "validation-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
$remoteCommand = @"
set -eu
chmod 0600 '$remoteRoot/inventories/validation/group_vars/all/vault.yml'
cd '$remoteRoot'
ANSIBLE_ROLES_PATH='$remoteRoot/roles' ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/validation/hosts.yml \
  playbooks/maintenance-window.yml \
  -e maintenance_authorized=true \
  -e maintenance_change_reference='$changeReference' \
  -e maintenance_apply_os_updates=$applyUpdatesValue \
  -e maintenance_refresh_container_images=$refreshImagesValue \
  -e maintenance_run_external_backup=$externalBackupValue
"@ -replace "`r`n", "`n"
& ssh.exe @sshOptions $controller $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Maintenance window validation failed.'
}

$platform = "automation@$($configuration.platform_ip)"
$postValidation = @"
set -eu
test -s /var/lib/node_exporter/textfile_collector/maintenance.prom
grep -q '^infrastructure_maintenance_last_run_success 1$' \
  /var/lib/node_exporter/textfile_collector/maintenance.prom
latest=`$(find /var/log/infrastructure-platform/maintenance \
  -maxdepth 1 -type f -name 'maintenance-*.json' | sort | tail -n 1)
test -n "`$latest"
jq -e '(.recovery_points | length) == 3 and
  (.health_checks | length) == 5' "`$latest" >/dev/null
test -z "`$(docker ps --all --format '{{.Names}}|{{.Status}}' |
  awk '`$0 ~ /unhealthy|Exited|Dead/ { print }')"
"@ -replace "`r`n", "`n"
$remoteCommand = @"
set -eu
ssh -o BatchMode=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  $platform \
  "sudo bash -s" <<'VALIDATE'
$postValidation
VALIDATE
"@ -replace "`r`n", "`n"
& ssh.exe @sshOptions $controller $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Post-maintenance evidence or service validation failed.'
}

Write-Host (
    "Maintenance validation completed successfully: $changeReference"
) -ForegroundColor Green
