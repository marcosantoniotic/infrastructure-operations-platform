[CmdletBinding()]
param(
    [switch]$VerifyIdempotence,
    [switch]$VerifyPersistence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configuration = Get-Content (Join-Path $validationRoot 'vagrant.json') -Raw |
    ConvertFrom-Json
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVars = Join-Path $ansibleRoot 'group_vars\all\main.yml'
$vaultFile = Join-Path $ansibleRoot 'group_vars\all\vault.yml'
$playbook = Join-Path $projectRoot 'playbooks\cockpit.yml'
$cockpitRole = Join-Path $projectRoot 'roles\cockpit'
$traefikRole = Join-Path $projectRoot 'roles\traefik'
$traefikRunner = Join-Path $PSScriptRoot 'Run-ValidationTraefik.ps1'
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$options = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL'
)

foreach ($path in @($privateKey, $inventory, $groupVars, $vaultFile, $playbook, $traefikRunner)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}

$content = Get-Content -LiteralPath $groupVars -Raw
$pattern = '(?ms)^# BEGIN VALIDATION COCKPIT\r?\n.*?^# END VALIDATION COCKPIT\r?\n?'
$content = [regex]::Replace($content, $pattern, '')
$section = @'
# BEGIN VALIDATION COCKPIT
cockpit_hostname: cockpit.localhost
cockpit_enable_traefik: true
cockpit_direct_firewall_access: false
cockpit_login_title: Infrastructure Operations Platform
cockpit_validation_address: 127.0.0.1
cockpit_validation_port: 9091
cockpit_listen_port: 9091
traefik_enable_cockpit: true
traefik_cockpit_hostname: cockpit.localhost
traefik_cockpit_backend_url: https://host.containers.internal:9091
# END VALIDATION COCKPIT
'@
$utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
[IO.File]::WriteAllText($groupVars, $content.TrimEnd() + "`n`n" + $section, $utf8)

& $traefikRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Traefik validation failed before Cockpit execution.'
}

& ssh.exe @options $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; sudo chown -R automation:automation $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller.' }

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/cockpit.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
    @{ Source = $vaultFile; Target = "$remoteRoot/inventories/validation/group_vars/all/vault.yml" }
)) {
    & scp.exe @options $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $($copy.Source)." }
}
foreach ($role in @($cockpitRole, $traefikRole)) {
    & scp.exe @options -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $role." }
}

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    & ssh.exe @options $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/cockpit.yml"
    if ($LASTEXITCODE -ne 0) { throw "Cockpit automation failed on pass $run." }
}

if ($VerifyPersistence) {
    Push-Location $vagrantRoot
    try {
        & vagrant.exe reload srv01-validation --no-provision
        if ($LASTEXITCODE -ne 0) { throw 'Failed to reload srv01-validation.' }
    }
    finally {
        Pop-Location
    }

    & ssh.exe @options $controller `
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null automation@$($configuration.platform_ip) 'sudo systemctl is-enabled cockpit.socket && sudo systemctl is-active cockpit.socket && curl --fail --silent --show-error --insecure https://127.0.0.1:9091/ping >/dev/null'"
    if ($LASTEXITCODE -ne 0) {
        throw 'Cockpit persistence validation failed after VM reload.'
    }
}

Write-Host 'Cockpit validation completed successfully.' -ForegroundColor Green
