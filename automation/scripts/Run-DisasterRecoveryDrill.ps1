[CmdletBinding()]
param(
    [switch]$SkipPlatformRebuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$configurationFile = Join-Path $validationRoot 'vagrant.json'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$sourceGroupVars = Join-Path $validationRoot 'ansible\group_vars\all\main.yml'
$sourceVault = Join-Path $validationRoot 'ansible\group_vars\all\vault.yml'
$sourceExternalVault = Join-Path $validationRoot 'ansible\group_vars\all\external-backup-vault.yml'
$recoveryRoot = Join-Path $validationRoot 'recovery'
$recoveryInventory = Join-Path $recoveryRoot 'hosts.yml'
$recoveryGroupVars = Join-Path $recoveryRoot 'group_vars\all\main.yml'
$evidenceFile = Join-Path $recoveryRoot 'evidence.json'
$remoteRoot = '/home/automation/infrastructure-operations-platform-recovery'
$utf8 = New-Object Text.UTF8Encoding($false)

foreach ($requiredFile in @(
    $configurationFile,
    $privateKey,
    $sourceGroupVars,
    $sourceVault,
    $sourceExternalVault,
    (Join-Path $projectRoot 'playbooks\platform.yml'),
    (Join-Path $projectRoot 'playbooks\external-backup.yml'),
    (Join-Path $projectRoot 'playbooks\recovery-drill.yml')
)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required recovery file was not found: $requiredFile"
    }
}

$configuration = Get-Content -LiteralPath $configurationFile -Raw |
    ConvertFrom-Json
if (-not $configuration.recovery_ip) {
    throw 'recovery_ip is not configured in .validation/vagrant.json.'
}
if ($configuration.recovery_ip -eq $configuration.platform_ip) {
    throw 'Recovery and validation hosts must use different addresses.'
}

$controller = "automation@$($configuration.controller_ip)"
$sshOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL'
)

New-Item -ItemType Directory -Path (
    Split-Path -Parent $recoveryGroupVars
) -Force | Out-Null

$inventoryContent = @"
---
all:
  children:
    platform:
      hosts:
        srv01-recovery:
          ansible_host: "$($configuration.recovery_ip)"
          ansible_user: automation
          ansible_become: true
          ansible_ssh_private_key_file: /home/automation/.ssh/id_ed25519
          ansible_ssh_common_args: >-
            -o BatchMode=yes
            -o StrictHostKeyChecking=no
            -o UserKnownHostsFile=/dev/null
"@
[IO.File]::WriteAllText($recoveryInventory, $inventoryContent, $utf8)

$groupVarsContent = Get-Content -LiteralPath $sourceGroupVars -Raw
$sectionPattern = '(?ms)^# BEGIN RECOVERY DRILL\r?\n.*?^# END RECOVERY DRILL\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$recoverySection = @'
# BEGIN RECOVERY DRILL
platform_hostname: srv01-recovery
external_backup_timer_enabled: false
recovery_drill_authorized: true
recovery_drill_expected_hostname: srv01-recovery
# END RECOVERY DRILL
'@
[IO.File]::WriteAllText(
    $recoveryGroupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $recoverySection + "`n",
    $utf8
)

$startedAt = [DateTimeOffset]::UtcNow
$result = 'failed'

try {
    $remoteCommand = @"
set -eu
case '$remoteRoot' in
  /home/automation/infrastructure-operations-platform-recovery) ;;
  *) echo 'Unsafe remote recovery root.' >&2; exit 20 ;;
esac
sudo rm -rf '$remoteRoot'
install -d -m 0755 \
  '$remoteRoot' \
  '$remoteRoot/inventories/recovery/group_vars/all'
sudo chown -R automation:automation '$remoteRoot'
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to prepare the controller recovery workspace.'
    }

    foreach ($directory in @('roles', 'playbooks')) {
        & scp.exe @sshOptions -r (
            Join-Path $projectRoot $directory
        ) "${controller}:$remoteRoot/"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to stage $directory."
        }
    }

    foreach ($copy in @(
        @{
            Source = (Join-Path $projectRoot 'requirements.yml')
            Target = "$remoteRoot/requirements.yml"
        },
        @{
            Source = $recoveryInventory
            Target = "$remoteRoot/inventories/recovery/hosts.yml"
        },
        @{
            Source = $recoveryGroupVars
            Target = "$remoteRoot/inventories/recovery/group_vars/all/main.yml"
        },
        @{
            Source = $sourceVault
            Target = "$remoteRoot/inventories/recovery/group_vars/all/vault.yml"
        },
        @{
            Source = $sourceExternalVault
            Target = "$remoteRoot/inventories/recovery/group_vars/all/external-backup-vault.yml"
        }
    )) {
        & scp.exe @sshOptions $copy.Source "${controller}:$($copy.Target)"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to stage $($copy.Source)."
        }
    }

    $remoteCommand = @"
set -eu
chmod 0600 \
  '$remoteRoot/inventories/recovery/group_vars/all/vault.yml' \
  '$remoteRoot/inventories/recovery/group_vars/all/external-backup-vault.yml'
cd '$remoteRoot'
ansible-galaxy collection install -r requirements.yml
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to prepare Ansible requirements.'
    }

    if (-not $SkipPlatformRebuild) {
        $remoteCommand = @"
set -eu
cd '$remoteRoot'
ANSIBLE_ROLES_PATH='$remoteRoot/roles' ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/recovery/hosts.yml \
  playbooks/platform.yml
"@ -replace "`r`n", "`n"
        & ssh.exe @sshOptions $controller $remoteCommand
        if ($LASTEXITCODE -ne 0) {
            throw 'Recovery platform reconstruction failed.'
        }
    }

    $remoteCommand = @"
set -eu
cd '$remoteRoot'
ANSIBLE_ROLES_PATH='$remoteRoot/roles' ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/recovery/hosts.yml \
  playbooks/external-backup.yml \
  -e external_backup_timer_enabled=false \
  -e external_backup_run_now=false
ANSIBLE_ROLES_PATH='$remoteRoot/roles' ansible-playbook \
  --vault-password-file /home/automation/.ansible/vault-password \
  -i inventories/recovery/hosts.yml \
  playbooks/recovery-drill.yml
"@ -replace "`r`n", "`n"
    & ssh.exe @sshOptions $controller $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw 'Encrypted recovery or application validation failed.'
    }

    $result = 'success'
}
finally {
    $completedAt = [DateTimeOffset]::UtcNow
    $drillType = if ($SkipPlatformRebuild) {
        'isolated-full-application-recovery'
    }
    else {
        'isolated-platform-reconstruction-and-application-recovery'
    }
    $evidence = [ordered]@{
        schema_version = 2
        drill_type = $drillType
        target = 'srv01-recovery'
        platform_rebuild_included = -not $SkipPlatformRebuild
        started_utc = $startedAt.ToString('o')
        completed_utc = $completedAt.ToString('o')
        duration_seconds = [math]::Round(
            ($completedAt - $startedAt).TotalSeconds
        )
        result = $result
        recovered_components = @('netbox', 'zabbix', 'grafana', 'prometheus')
        secret_material_recorded = $false
    }
    [IO.File]::WriteAllText(
        $evidenceFile,
        ($evidence | ConvertTo-Json -Depth 4),
        $utf8
    )
}

Write-Host 'Isolated disaster recovery drill completed successfully.' -ForegroundColor Green
Write-Host "Sanitized local evidence: $evidenceFile"
