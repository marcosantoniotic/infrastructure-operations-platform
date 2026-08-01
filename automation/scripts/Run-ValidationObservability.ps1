[CmdletBinding()]
param(
    [switch]$EnableTraefik,
    [switch]$EnableEmailAlerts,
    [string]$AlertmanagerSmtpUsername = $env:ALERTMANAGER_SMTP_USERNAME,
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
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$credentialFile = Join-Path $validationRoot 'grafana-initial-credentials.txt'
$vaultAdditionsFile = Join-Path $ansibleRoot 'observability-vault-additions.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\observability.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$observabilityRole = Join-Path $projectRoot 'roles\observability'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$traefikRunner = Join-Path $PSScriptRoot 'Run-ValidationTraefik.ps1'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $inventory,
    $requirements,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}
foreach ($path in @($dockerRole, $observabilityRole)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Required role not found: $path"
    }
}

function New-RandomSecret {
    param([ValidateRange(24, 128)][int]$ByteCount = 36)
    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Set-CurrentUserFileAcl {
    param([Parameter(Mandatory)][string]$Path)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path /inheritance:r /grant:r "${identity}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restrict the local ACL: $Path"
    }
}

& $preflightRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before observability execution.'
}

if ($EnableTraefik) {
    & $traefikRunner
    if ($LASTEXITCODE -notin @(0, $null)) {
        throw 'Traefik validation failed before observability execution.'
    }
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

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false

$traefikVariables = @('observability_enable_traefik: false')
if ($EnableTraefik) {
    $traefikVariables = @(
        'observability_enable_traefik: true'
        'observability_grafana_hostname: grafana.localhost'
        'observability_traefik_network: proxy'
        'observability_traefik_middlewares:'
        '  - security-headers@file'
        'observability_traefik_validation_address: 127.0.0.1'
        'observability_traefik_https_port: 8443'
    )
}
$traefikVariablesYaml = $traefikVariables -join "`n"

$alertmanagerVariables = @('observability_alertmanager_enabled: false')
if ($EnableEmailAlerts) {
    if ([string]::IsNullOrWhiteSpace($AlertmanagerSmtpUsername)) {
        throw 'Provide -AlertmanagerSmtpUsername or set ALERTMANAGER_SMTP_USERNAME.'
    }
    $smtpPassword = ([string](Get-Clipboard -Raw)).Trim()
    if ($smtpPassword.Length -lt 16) {
        throw 'Copy the Brevo SMTP key from the password manager before using -EnableEmailAlerts.'
    }
    $alertmanagerVariables = @(
        'observability_alertmanager_enabled: true'
        'observability_alertmanager_image: prom/alertmanager:v0.32.1'
        'observability_alertmanager_bind_address: 127.0.0.1'
        'observability_alertmanager_port: 9093'
        'observability_alertmanager_smtp_smarthost: smtp-relay.brevo.com:587'
        'observability_alertmanager_smtp_from: alerts@marnep.com.br'
        "observability_alertmanager_smtp_username: `"$AlertmanagerSmtpUsername`""
        'observability_alertmanager_smtp_password: "{{ vault_alertmanager_smtp_password }}"'
        'observability_alertmanager_email_to: alerts@marnep.com.br'
        'observability_alertmanager_critical_group_wait: 15s'
        'observability_alertmanager_critical_repeat_interval: 4h'
        'observability_alertmanager_warning_group_wait: 2m'
        'observability_alertmanager_warning_repeat_interval: 12h'
    )
}
$alertmanagerVariablesYaml = $alertmanagerVariables -join "`n"

$groupVarsContent = if (Test-Path -LiteralPath $groupVars) {
    Get-Content -LiteralPath $groupVars -Raw
}
else {
    "---`n"
}
$sectionPattern = '(?ms)^# BEGIN VALIDATION OBSERVABILITY\r?\n.*?^# END VALIDATION OBSERVABILITY\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$observabilitySection = @"
# BEGIN VALIDATION OBSERVABILITY
observability_project_dir: /opt/observability
observability_prometheus_image: prom/prometheus:v3.13.1
observability_grafana_image: grafana/grafana:13.1.1
observability_node_exporter_image: prom/node-exporter:v1.12.1
observability_cadvisor_image: ghcr.io/google/cadvisor:v0.60.5
observability_blackbox_image: prom/blackbox-exporter:v0.28.0
$alertmanagerVariablesYaml
observability_scrape_interval: 30s
observability_prometheus_retention_time: 30d
observability_prometheus_retention_size: 8GB
observability_prometheus_bind_address: 127.0.0.1
observability_prometheus_port: 9090
observability_grafana_bind_address: 127.0.0.1
observability_grafana_port: 3000
observability_grafana_admin_user: admin
observability_grafana_admin_password: "{{ vault_grafana_admin_password }}"
observability_blackbox_targets:
  - name: prometheus
    url: http://prometheus:9090/-/ready
  - name: grafana
    url: http://grafana:3000/api/health
  - name: netbox
    url: http://netbox:8080/login/
    host_header: netbox.localhost
  - name: zabbix
    url: http://zabbix-web:8080/
  - name: portainer
    url: http://portainer:9000/
  - name: traefik
    url: http://traefik:8082/metrics
  - name: cockpit
    url: https://host.containers.internal:9091/ping
    tls_insecure: true
observability_dns_targets:
  - name: dns-standby
    address: $($configuration.standby_ip):53
    query_name: example.com
    query_type: A
$traefikVariablesYaml
# END VALIDATION OBSERVABILITY
"@
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $observabilitySection,
    $utf8WithoutBom
)

$adminCredential = New-RandomSecret
$vaultAdditions = "vault_grafana_admin_password: `"$adminCredential`"`n"
if ($EnableEmailAlerts) {
    $escapedSmtpPassword = $smtpPassword.Replace('"', '\"')
    $vaultAdditions += "vault_alertmanager_smtp_password: `"$escapedSmtpPassword`"`n"
    Set-Clipboard -Value 'CLEARED'
    Remove-Variable smtpPassword, escapedSmtpPassword -ErrorAction SilentlyContinue
}
[IO.File]::WriteAllText($vaultAdditionsFile, $vaultAdditions, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultAdditionsFile

if (-not (Test-Path -LiteralPath $vaultPasswordFile -PathType Leaf)) {
    [IO.File]::WriteAllText(
        $vaultPasswordFile,
        (New-RandomSecret -ByteCount 48),
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $vaultPasswordFile
}

Write-Host 'Preparing observability automation and Vault on the controller.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/automation/.ansible; sudo chown -R automation:automation $remoteRoot/roles; chmod -R u+rwX $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller directories.' }

& scp.exe @commonOptions $vaultPasswordFile "${controller}:/tmp/platform-vault-password"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }
& scp.exe @commonOptions $vaultAdditionsFile "${controller}:/tmp/observability-vault-additions.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage observability Vault additions.' }
if (Test-Path -LiteralPath $vaultFile -PathType Leaf) {
    & scp.exe @commonOptions $vaultFile "${controller}:/tmp/platform-vault.yml"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
}

$vaultMergeScript = @"
set -e
remote_root=$remoteRoot
vault_key_path=/home/automation/.ansible/vault-password
vault_target=`$remote_root/inventories/validation/group_vars/all/vault.yml
install -m 0600 /tmp/platform-vault-password "`$vault_key_path"
if [ -s /tmp/platform-vault.yml ]; then
  ansible-vault decrypt /tmp/platform-vault.yml \
    --vault-password-file "`$vault_key_path" \
    --output /tmp/platform-vault-plain.yml
else
  printf '%s\n' '---' > /tmp/platform-vault-plain.yml
fi
if ! grep -q '^vault_grafana_admin_password:' /tmp/platform-vault-plain.yml; then
  grep '^vault_grafana_admin_password:' /tmp/observability-vault-additions.yml \
    >> /tmp/platform-vault-plain.yml
  printf '%s\n' created > /tmp/grafana-secret-state
else
  printf '%s\n' existing > /tmp/grafana-secret-state
fi
if grep -q '^vault_alertmanager_smtp_password:' /tmp/observability-vault-additions.yml; then
  sed -i '/^vault_alertmanager_smtp_password:/d' /tmp/platform-vault-plain.yml
  grep '^vault_alertmanager_smtp_password:' /tmp/observability-vault-additions.yml \
    >> /tmp/platform-vault-plain.yml
fi
ansible-vault encrypt /tmp/platform-vault-plain.yml \
  --vault-password-file "`$vault_key_path" \
  --output "`$vault_target"
chmod 0600 "`$vault_target"
rm -f /tmp/platform-vault.yml /tmp/platform-vault-plain.yml \
  /tmp/platform-vault-password /tmp/observability-vault-additions.yml
"@
$vaultMergeScript = $vaultMergeScript -replace "`r`n", "`n"
$vaultMergeScriptFile = Join-Path $ansibleRoot 'observability-merge-vault.sh'
[IO.File]::WriteAllText($vaultMergeScriptFile, $vaultMergeScript, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultMergeScriptFile
& scp.exe @commonOptions $vaultMergeScriptFile "${controller}:/tmp/observability-merge-vault.sh"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault merge script.' }
& ssh.exe @commonOptions $controller `
    "bash /tmp/observability-merge-vault.sh; rc=`$?; rm -f /tmp/observability-merge-vault.sh; exit `$rc"
if ($LASTEXITCODE -ne 0) { throw 'Failed to merge Grafana secret into Vault.' }
& scp.exe @commonOptions `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" `
    $vaultFile
if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve the encrypted Vault locally.' }
Set-CurrentUserFileAcl -Path $vaultFile

$secretState = (& ssh.exe @commonOptions $controller 'cat /tmp/grafana-secret-state').Trim()
& ssh.exe @commonOptions $controller 'rm -f /tmp/grafana-secret-state'
Remove-Item -LiteralPath $vaultAdditionsFile, $vaultMergeScriptFile -Force

if ($secretState -eq 'created') {
    [IO.File]::WriteAllText(
        $credentialFile,
        "Grafana URL: https://grafana.localhost:8443/`r`nPrometheus fallback (via SSH tunnel): http://127.0.0.1:9090`r`nUsername: admin`r`nPassword: $adminCredential`r`n",
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $credentialFile
}
elseif (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
    throw 'The Grafana secret exists in Vault, but the local credential record is unavailable.'
}

foreach ($copy in @(
    @{ Source = $requirements; Target = "$remoteRoot/requirements.yml" }
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/observability.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
)) {
    & scp.exe @commonOptions $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage: $($copy.Source)" }
}
foreach ($role in @($dockerRole, $observabilityRole)) {
    & scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage role: $role" }
}

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to install required Ansible collections.' }

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing observability automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/observability.yml"
    if ($LASTEXITCODE -ne 0) {
        throw "Observability automation failed on pass $run."
    }

    if ($run -eq 1 -and $VerifyPersistence) {
        Write-Host 'Reloading SRV01-VALIDATION to verify observability persistence.'
        Push-Location $vagrantRoot
        try {
            & vagrant.exe reload srv01-validation --no-provision
            if ($LASTEXITCODE -ne 0) {
                throw 'Vagrant reload failed during observability persistence validation.'
            }
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host "Grafana initial credentials: $credentialFile"
Write-Warning 'Store the credential in a password manager and remove the local credential file.'
Write-Host 'Observability validation completed successfully.' -ForegroundColor Green
